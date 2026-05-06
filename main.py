from __future__ import annotations

import logging
import os
import random
import shlex
import sys
import time
from collections import Counter
from dataclasses import dataclass
from datetime import date
from getpass import getpass
from pathlib import Path
from typing import Any

import pandas as pd
import typer
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from rich.table import Table
from rich.panel import Panel
from rich.console import Group
from rich.text import Text
from rich.live import Live
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn, TimeElapsedColumn

try:
    import msvcrt
except ImportError:  # pragma: no cover - fallback for non-Windows envs
    msvcrt = None

from cache.cache_loader import delete_contracheque_cache, load_contracheque_cache
from cache.data_loader import count_cache_candidates, load_cache_candidates, load_cache_items
from cache.json_builder import build_cache_payloads
from config import load_settings
from db.oracle_conn import create_oracle_engine, initialize_oracle_session, resolve_oracle_object_name
from db.postgres_conn import create_postgres_engine, reflect_metadata
from db.schema_sql import build_normalized_postgres_schema_sql, write_schema_sql_file
from extract.contracheques import count_contracheques, extract_contracheques, iter_contracheques
from extract.folhas import count_folhas, extract_folhas
from load.carga_loader import finalizar_carga, iniciar_carga, registrar_erros
from load.consolidado_loader import load_consolidados, prepare_consolidados
from load.contracheque_loader import fetch_contracheque_map, load_contracheques, prepare_contracheques
from load.folha_loader import fetch_folha_map, load_folhas
from load.item_loader import load_itens, prepare_itens
from load.rubrica_loader import fetch_rubrica_map, load_rubricas
from load.servidor_loader import fetch_servidor_map, load_servidores
from load.snapshot_loader import load_snapshots, prepare_snapshots
from load.vinculo_loader import fetch_vinculo_map, load_vinculos, prepare_vinculos
from transform.contracheque_transform import transform_contracheques
from transform.folhas_transform import transform_folhas
from transform.item_transform import transform_itens
from transform.rubrica_transform import transform_rubricas
from transform.servidor_transform import transform_servidores
from transform.snapshot_transform import transform_snapshots
from transform.vinculo_transform import transform_vinculos
from utils.logger import console, setup_logger
from utils.normalizers import normalize_folha_description
from utils.validators import validate_date_range, validate_month, validate_year
from validation.contracheque_analysis import ValidationAccumulator
from validation.folha_analysis import analyze_folhas_por_mes, build_folha_lookup
from validation.report import render_validation_report, write_validation_report_markdown


VALIDATION_CHUNK_SIZE = 5000
CACHE_BATCH_SIZE = 1000
app = typer.Typer(add_completion=False)
EASTER_EGG_CODE = "vector"


@dataclass(slots=True)
class RunOptions:
    ano: int
    mes: int | None = None
    data_inicio: str | None = None
    data_fim: str | None = None
    generate_cache: bool = False
    refresh_cache_competencia: bool = False
    refresh_cache_matricula: str | None = None
    refresh_cache_ano: bool = False
    force_year_refresh: bool = False
    report_md: bool = False
    dry_run: bool = False
    validate_only: bool = False
    verbose: bool = False

    def to_kwargs(self) -> dict[str, Any]:
        return {
            "ano": self.ano,
            "mes": self.mes,
            "data_inicio": self.data_inicio,
            "data_fim": self.data_fim,
            "generate_cache": self.generate_cache,
            "refresh_cache_competencia": self.refresh_cache_competencia,
            "refresh_cache_matricula": self.refresh_cache_matricula,
            "refresh_cache_ano": self.refresh_cache_ano,
            "force_year_refresh": self.force_year_refresh,
            "report_md": self.report_md,
            "dry_run": self.dry_run,
            "validate_only": self.validate_only,
            "verbose": self.verbose,
        }


@dataclass(slots=True)
class PostgresConnectionPrompt:
    host: str
    port: int
    database: str
    user: str
    password: str
    schema: str = "public"


def _log_counts(logger: logging.Logger, folhas_df: pd.DataFrame, contracheques_df: pd.DataFrame) -> None:
    logger.info("Folhas extraidas: %s", len(folhas_df))
    logger.info("Contracheques extraidos: %s", len(contracheques_df))

def _add_servidor_ids(df: pd.DataFrame, servidor_map: dict[int, int]) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    enriched = df.copy()
    enriched["id_servidor"] = enriched["numfunc"].map(servidor_map)
    return enriched


def _build_folha_desc_map(folhas_df: pd.DataFrame, folha_map: dict[tuple, int]) -> tuple[dict[tuple, int], dict[date, int]]:
    desc_map: dict[tuple, int] = {}
    por_mes: dict[date, list[int]] = {}
    for row in folhas_df.to_dict(orient="records"):
        id_folha = folha_map.get((row["mes_ano_folha"], row["num_folha"]))
        if id_folha is None:
            continue
        desc_map[(row["mes_ano_folha"], normalize_folha_description(row["descricao_folha"]))] = id_folha
        por_mes.setdefault(row["mes_ano_folha"], []).append(id_folha)
    unica = {mes: ids[0] for mes, ids in por_mes.items() if len(set(ids)) == 1}
    return desc_map, unica


def _summary_table(summary: dict[str, Any]) -> Table:
    table = Table(title="Resumo da Execucao")
    table.add_column("Metrica")
    table.add_column("Valor", justify="right")
    for key, value in summary.items():
        table.add_row(key, str(value))
    return table


def _run_with_status(message: str, action, *args, **kwargs):
    with console.status(f"[bold cyan]{message}[/bold cyan]", spinner="dots"):
        return action(*args, **kwargs)


def _build_progress() -> Progress:
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=30),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    )


def _help_flags_table() -> Table:
    table = Table(title="Flags Disponiveis")
    table.add_column("Flag")
    table.add_column("Uso")
    table.add_column("Observacao")
    table.add_row("--ano", "Define o ano a processar.", "Obrigatoria no modo por flags.")
    table.add_row("--mes", "Restringe o processamento a um mes.", "Aceita valores de 1 a 12.")
    table.add_row("--data-inicio", "Define a data inicial do recorte.", "Use junto com --data-fim.")
    table.add_row("--data-fim", "Define a data final do recorte.", "Use junto com --data-inicio.")
    table.add_row("--verbose", "Ativa logs detalhados.", "Recomendado em execucoes reais.")
    table.add_row("--validate-only", "Executa apenas diagnostico.", "Nao grava no PostgreSQL.")
    table.add_row("--dry-run", "Extrai e transforma sem gravar.", "Nao grava no PostgreSQL.")
    table.add_row("--report-md", "Gera relatorio Markdown.", "Mais util com --validate-only.")
    table.add_row("--generate-cache", "Gera JSON em contracheque_cache.", "Le dados normalizados do PostgreSQL.")
    table.add_row(
        "--refresh-cache-competencia",
        "Limpa e regenera o cache da competencia.",
        "Exige --generate-cache e --mes.",
    )
    table.add_row(
        "--refresh-cache-matricula",
        "Limpa e regenera o cache de uma matricula.",
        "Exige --generate-cache, --mes e matricula.",
    )
    table.add_row(
        "--refresh-cache-ano",
        "Limpa e regenera o cache do ano.",
        "Exige --generate-cache e nao aceita --mes.",
    )
    table.add_row(
        "--force-year-refresh",
        "Confirma refresh anual explicitamente.",
        "Obrigatoria com --refresh-cache-ano.",
    )
    return table


def _help_examples_table() -> Table:
    table = Table(title="Exemplos de Uso")
    table.add_column("Objetivo")
    table.add_column("Comando")
    table.add_row("Abrir menu interativo", "python main.py")
    table.add_row(
        "Gerar schema PostgreSQL",
        "Use o menu: [8] Gerar schema PostgreSQL normalizado",
    )
    table.add_row("Migracao real", "python main.py --ano 2026 --verbose")
    table.add_row("Validacao pre-carga", "python main.py --ano 2026 --validate-only --verbose")
    table.add_row("Dry-run", "python main.py --ano 2026 --mes 1 --dry-run --verbose")
    table.add_row(
        "Gerar cache JSON",
        "python main.py --ano 2026 --mes 1 --generate-cache --verbose",
    )
    table.add_row(
        "Refresh por competencia",
        "python main.py --ano 2026 --mes 1 --generate-cache --refresh-cache-competencia --verbose",
    )
    table.add_row(
        "Refresh por matricula",
        "python main.py --ano 2026 --mes 1 --generate-cache --refresh-cache-matricula 123456 --verbose",
    )
    table.add_row(
        "Refresh por ano",
        "python main.py --ano 2026 --generate-cache --refresh-cache-ano --force-year-refresh --verbose",
    )
    return table


def _show_help_screen() -> None:
    _clear_screen()
    _print_menu_header(
        "Ajuda",
        "Consulte as flags reais da CLI e os exemplos mais comuns de execucao.",
    )
    console.print("[bold]Comando base[/bold]: python main.py")
    console.print(
        "[dim]Sem flags abre o menu interativo. Com flags validas, executa diretamente no modo scriptado.[/dim]\n"
    )
    console.print(_help_flags_table())
    console.print()
    console.print(_help_examples_table())
    console.print()
    console.print(
        "[dim]Dica: use o menu para operacao assistida e o modo por flags para automacao, agendamentos e repeticao controlada.[/dim]"
    )
    console.print(
        "[dim]O menu tambem permite gerar e aplicar o schema PostgreSQL normalizado no banco de destino com confirmacao explicita.[/dim]"
    )
    console.input("\nPressione Enter para voltar ao menu principal...")


def _build_snake_renderable(
    width: int,
    height: int,
    snake: list[tuple[int, int]],
    food: tuple[int, int],
    score: int,
    message: str | None = None,
) -> Group:
    title = Text("Hidden Diagnostic Mode", style="bold magenta")
    subtitle = Text("Diagnostic Console | Snake Mode", style="bold cyan")
    contacts = Table.grid(padding=(0, 1))
    contacts.add_row("Mode:", "Diagnostics")
    contacts.add_row("Controls:", "W A S D or arrow keys")
    contacts.add_row("Exit:", "Q")

    board = []
    snake_head = snake[0]
    snake_body = set(snake[1:])
    for y in range(height):
        row = []
        for x in range(width):
            if (x, y) == snake_head:
                row.append("[bold green]@[/bold green]")
            elif (x, y) in snake_body:
                row.append("[green]o[/green]")
            elif (x, y) == food:
                row.append("[bold red]*[/bold red]")
            else:
                row.append("[dim].[/dim]")
        board.append("".join(row))

    board_text = "\n".join(board)
    footer = message or "Controles: W A S D ou setas | Q sai"
    info = Text(f"Score: {score}\n{footer}", style="bold yellow")

    return Group(
        Panel.fit(Group(title, subtitle, contacts), border_style="blue", title="Perfil do Criador"),
        Panel(board_text, border_style="green", title="Cobrinha"),
        Panel(info, border_style="yellow", title="Status"),
    )


def _spawn_food(width: int, height: int, snake: list[tuple[int, int]]) -> tuple[int, int]:
    available = [(x, y) for x in range(width) for y in range(height) if (x, y) not in snake]
    return random.choice(available) if available else (-1, -1)


def _clear_keyboard_buffer() -> None:
    if msvcrt is None:
        return
    while msvcrt.kbhit():
        try:
            msvcrt.getwch()
        except OSError:
            break


def _initial_snake_state(width: int, height: int) -> tuple[list[tuple[int, int]], tuple[int, int], int]:
    snake = [(width // 2, height // 2), (width // 2 - 1, height // 2), (width // 2 - 2, height // 2)]
    return snake, (1, 0), 0


def _run_secret_snake_mode() -> bool:
    width = 24
    height = 12
    snake, direction, score = _initial_snake_state(width, height)
    food = _spawn_food(width, height, snake)
    message = None

    with Live(_build_snake_renderable(width, height, snake, food, score, message), console=console, refresh_per_second=10) as live:
        while True:
            next_direction = _read_snake_key(direction)
            if next_direction is None:
                _clear_keyboard_buffer()
                console.print("\n[bold magenta]Modo secreto encerrado. Vida longa e prospera, Eremita.[/bold magenta]")
                return True
            if next_direction == direction:
                pass
            elif next_direction == ("restart", "restart"):
                snake, direction, score = _initial_snake_state(width, height)
                food = _spawn_food(width, height, snake)
                message = "Jogo reiniciado. Agora vai."
                live.update(_build_snake_renderable(width, height, snake, food, score, message))
                time.sleep(0.12)
                continue
            direction = next_direction

            head_x, head_y = snake[0]
            next_head = (head_x + direction[0], head_y + direction[1])

            if not (0 <= next_head[0] < width and 0 <= next_head[1] < height) or next_head in snake:
                message = "Game over. Pressione Q para sair ou R para reiniciar."
                live.update(_build_snake_renderable(width, height, snake, food, score, message))
                while True:
                    if msvcrt is not None and msvcrt.kbhit():
                        key = msvcrt.getwch().lower()
                        if key == "q":
                            _clear_keyboard_buffer()
                            console.print("\n[bold magenta]Modo secreto encerrado. Ate a proxima, Eremita.[/bold magenta]")
                            return True
                        if key == "r":
                            _clear_keyboard_buffer()
                            snake, direction, score = _initial_snake_state(width, height)
                            food = _spawn_food(width, height, snake)
                            message = "Jogo reiniciado. Porque desistir seria sem graca."
                            live.update(_build_snake_renderable(width, height, snake, food, score, message))
                            time.sleep(0.12)
                            break
                    time.sleep(0.05)
                continue

            snake.insert(0, next_head)
            if next_head == food:
                score += 1
                food = _spawn_food(width, height, snake)
                message = "Acertou a comida. Continue. Porque voce pode."
            else:
                snake.pop()
                message = None

            live.update(_build_snake_renderable(width, height, snake, food, score, message))
            time.sleep(0.12)


def _read_snake_key(direction: tuple[int, int]) -> tuple[int, int] | None:
    if msvcrt is None or not msvcrt.kbhit():
        return direction

    key = msvcrt.getwch()
    if key in ("\x00", "\xe0"):
        key = msvcrt.getwch()
        return {
            "H": (0, -1),
            "P": (0, 1),
            "K": (-1, 0),
            "M": (1, 0),
        }.get(key, direction)

    key = key.lower()
    if key == "q":
        return None
    if key == "r":
        return ("restart", "restart")

    mapping = {
        "w": (0, -1),
        "s": (0, 1),
        "a": (-1, 0),
        "d": (1, 0),
    }
    next_direction = mapping.get(key, direction)
    if next_direction[0] == -direction[0] and next_direction[1] == -direction[1]:
        return direction
    return next_direction


def _normalize_manual_command(raw_command: str) -> list[str]:
    args = shlex.split(raw_command, posix=False)
    if not args:
        return []

    normalized = list(args)
    first = normalized[0].lower()
    if first in {"python", "python.exe", "py", "py.exe"}:
        normalized = normalized[1:]
        if normalized and normalized[0].lower().endswith("main.py"):
            normalized = normalized[1:]
    elif first.endswith("main.py"):
        normalized = normalized[1:]

    return normalized


def _execute_manual_command() -> bool:
    _clear_screen()
    _print_menu_header(
        "Executar Comando Manual",
        "Digite apenas as flags ou o comando completo (ex.: python main.py --ano 2026 --dry-run)",
    )
    console.print("[dim]Digite 'v' para voltar sem executar nada.[/dim]")
    raw_command = console.input("Comando manual (ex.: --ano 2026 --validate-only --verbose): ").strip()
    if raw_command.lower() == "v":
        return True
    if raw_command == "":
        console.print("[yellow]Nenhum comando informado.[/yellow]")
        return True
    if raw_command.lower() == EASTER_EGG_CODE:
        return _run_secret_snake_mode()

    args = _normalize_manual_command(raw_command)
    if not args:
        console.print("[yellow]Nenhuma flag foi identificada apos normalizar o comando.[/yellow]")
        return True

    console.print(f"[bold]Executando[/bold]: python main.py {' '.join(args)}")
    try:
        app(args=args, prog_name="python main.py", standalone_mode=False)
        console.print("\n[bold green]Execucao concluida.[/bold green]")
    except typer.Exit as exc:
        exit_code = exc.exit_code or 0
        if exit_code == 0:
            console.print("\n[bold green]Execucao concluida.[/bold green]")
        else:
            console.print(f"\n[bold red]Execucao finalizada com falha (codigo {exit_code}).[/bold red]")
    except Exception as exc:
        console.print(f"\n[bold red]Falha ao interpretar ou executar o comando: {exc}[/bold red]")
    return _post_execution_menu()


def _prompt_postgres_connection() -> PostgresConnectionPrompt | str:
    console.print("[bold]Destino PostgreSQL do schema normalizado[/bold]")
    host = _prompt_text("Host (ex.: 127.0.0.1)", required=True)
    if host == "back":
        return "back"

    port = _prompt_int("Porta (ex.: 5432, Enter = 5432)", required=False, min_value=1, max_value=65535)
    if port == "back":
        return "back"

    database = _prompt_text("Nome do banco (ex.: payroll_migration)", required=True)
    if database == "back":
        return "back"

    user = _prompt_text("Usuario (ex.: postgres)", required=True)
    if user == "back":
        return "back"

    console.print("[dim]A senha nao sera exibida nem registrada em log.[/dim]")
    password = getpass("Senha PostgreSQL (ou 'v' para voltar): ")
    if password.strip().lower() == "v":
        return "back"
    if password == "":
        console.print("[bold red]Senha obrigatoria.[/bold red]")
        return "back"

    schema = _prompt_text("Schema de destino (ex.: public, Enter = public)", required=False)
    if schema == "back":
        return "back"

    return PostgresConnectionPrompt(
        host=host,
        port=port or 5432,
        database=database,
        user=user,
        password=password,
        schema=schema or "public",
    )


def _build_postgres_engine_for_target(target: PostgresConnectionPrompt):
    dsn = URL.create(
        "postgresql+psycopg2",
        username=target.user,
        password=target.password,
        host=target.host,
        port=target.port,
        database=target.database,
    )
    return create_engine(dsn, future=True)


def _test_postgres_target_connection(target: PostgresConnectionPrompt) -> None:
    engine = _build_postgres_engine_for_target(target)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    finally:
        engine.dispose()


def _schema_summary_table(target: PostgresConnectionPrompt, table_count: int, index_count: int, foreign_key_count: int, unique_count: int) -> Table:
    table = Table(title="Resumo da Geracao do Schema")
    table.add_column("Item")
    table.add_column("Valor")
    table.add_row("Host", target.host)
    table.add_row("Porta", str(target.port))
    table.add_row("Banco", target.database)
    table.add_row("Usuario", target.user)
    table.add_row("Schema", target.schema)
    table.add_row("Tabelas previstas", str(table_count))
    table.add_row("Indices previstos", str(index_count))
    table.add_row("FKs previstas", str(foreign_key_count))
    table.add_row("Uniques previstas", str(unique_count))
    return table


def _execute_schema_sql_on_target(target: PostgresConnectionPrompt, sql: str) -> None:
    engine = _build_postgres_engine_for_target(target)
    raw_connection = engine.raw_connection()
    try:
        cursor = raw_connection.cursor()
        cursor.execute(sql)
        raw_connection.commit()
        cursor.close()
    except Exception:
        raw_connection.rollback()
        raise
    finally:
        raw_connection.close()
        engine.dispose()


def _run_schema_generation_menu() -> bool:
    _clear_screen()
    _print_menu_header(
        "Gerar Schema PostgreSQL Normalizado",
        "Gera o SQL estrutural completo e aplica no banco informado (ex.: host 127.0.0.1, banco payroll_migration).",
    )
    target = _prompt_postgres_connection()
    if target == "back":
        return True

    try:
        _test_postgres_target_connection(target)
        console.print("[bold green]Conexao com PostgreSQL validada com sucesso.[/bold green]")
    except Exception as exc:
        console.print(f"[bold red]Falha ao conectar no PostgreSQL de destino: {exc}[/bold red]")
        return True

    build_result = build_normalized_postgres_schema_sql(schema=target.schema)
    sql_file = write_schema_sql_file(build_result.sql, Path.cwd(), target.schema)
    console.print(_schema_summary_table(
        target,
        build_result.table_count,
        build_result.index_count,
        build_result.foreign_key_count,
        build_result.unique_constraint_count,
    ))
    console.print(f"\n[bold]Arquivo SQL gerado[/bold]: {sql_file}")

    confirm = _prompt_yes_no(
        "Deseja aplicar esse schema no banco informado agora?",
        default=False,
        allow_back=False,
    )
    if not confirm:
        console.print("[yellow]Execucao cancelada antes da aplicacao do schema.[/yellow]")
        return True

    try:
        _execute_schema_sql_on_target(target, build_result.sql)
        console.print("\n[bold green]Schema PostgreSQL normalizado aplicado com sucesso.[/bold green]")
        console.print(f"[green]Banco:[/green] {target.database}")
        console.print(f"[green]Host:[/green] {target.host}:{target.port}")
        console.print(f"[green]Schema:[/green] {target.schema}")
        console.print(f"[green]Tabelas previstas:[/green] {build_result.table_count}")
        console.print(f"[green]Indices previstos:[/green] {build_result.index_count}")
    except Exception as exc:
        console.print(f"\n[bold red]Falha ao aplicar o schema no PostgreSQL: {exc}[/bold red]")

    return _post_execution_menu()


def _print_menu_header(title: str, subtitle: str | None = None) -> None:
    content = title if subtitle is None else f"{title}\n{subtitle}"
    console.print(Panel.fit(content, title="ETL Contracheques", border_style="cyan"))


def _clear_screen() -> None:
    if os.name == "nt":
        os.system("cls")
    else:
        os.system("clear")
    console.clear()
    print("\033[2J\033[H", end="")


def _prompt_numeric_option(prompt: str, valid_options: set[str]) -> str:
    while True:
        value = console.input(f"{prompt} ").strip()
        if value in valid_options:
            return value
        console.print("[bold red]Opcao invalida.[/bold red] Informe uma das opcoes exibidas.")


def _prompt_int(
    label: str,
    *,
    required: bool = True,
    min_value: int | None = None,
    max_value: int | None = None,
    allow_back: bool = True,
) -> int | None | str:
    suffix = " (ou 'v' para voltar)" if allow_back else ""
    while True:
        raw = console.input(f"{label}{suffix}: ").strip()
        if allow_back and raw.lower() == "v":
            return "back"
        if raw == "":
            if not required:
                return None
            console.print("[bold red]Campo obrigatorio.[/bold red]")
            continue
        try:
            value = int(raw)
        except ValueError:
            console.print("[bold red]Informe um numero inteiro valido.[/bold red]")
            continue
        if min_value is not None and value < min_value:
            console.print(f"[bold red]Informe um valor maior ou igual a {min_value}.[/bold red]")
            continue
        if max_value is not None and value > max_value:
            console.print(f"[bold red]Informe um valor menor ou igual a {max_value}.[/bold red]")
            continue
        return value


def _prompt_text(label: str, *, required: bool = False, allow_back: bool = True) -> str | None:
    suffix = " (ou 'v' para voltar)" if allow_back else ""
    while True:
        value = console.input(f"{label}{suffix}: ").strip()
        if allow_back and value.lower() == "v":
            return "back"
        if value == "":
            if required:
                console.print("[bold red]Campo obrigatorio.[/bold red]")
                continue
            return None
        return value


def _prompt_yes_no(label: str, *, default: bool = False, allow_back: bool = True) -> bool | str:
    hint = "S/n" if default else "s/N"
    suffix = " ou 'v' para voltar" if allow_back else ""
    while True:
        value = console.input(f"{label} [{hint}{suffix}]: ").strip().lower()
        if allow_back and value == "v":
            return "back"
        if value == "":
            return default
        if value in {"s", "sim", "y", "yes"}:
            return True
        if value in {"n", "nao", "não", "no"}:
            return False
        console.print("[bold red]Responda com s ou n.[/bold red]")


def _prompt_optional_date_range() -> tuple[str | None, str | None] | str:
    use_range = _prompt_yes_no("Deseja informar recorte por data? (ex.: 2026-01-01 ate 2026-01-05)", default=False)
    if use_range == "back":
        return "back"
    if not use_range:
        return None, None
    data_inicio = _prompt_text("Data inicio (YYYY-MM-DD, ex.: 2026-01-01)", required=True)
    if data_inicio == "back":
        return "back"
    data_fim = _prompt_text("Data fim (YYYY-MM-DD, ex.: 2026-01-05)", required=True)
    if data_fim == "back":
        return "back"
    return data_inicio, data_fim


def _prompt_common_filters(*, require_month: bool = False, allow_date_range: bool = True) -> RunOptions | str:
    ano = _prompt_int("Ano (ex.: 2026)", min_value=1900, max_value=2999)
    if ano == "back":
        return "back"

    if require_month:
        mes = _prompt_int("Mes (ex.: 1)", min_value=1, max_value=12)
    else:
        mes = _prompt_int("Mes (ex.: 1, Enter = todos)", required=False, min_value=1, max_value=12)
    if mes == "back":
        return "back"

    data_inicio = None
    data_fim = None
    if allow_date_range:
        date_range = _prompt_optional_date_range()
        if date_range == "back":
            return "back"
        data_inicio, data_fim = date_range

    verbose = _prompt_yes_no("Ativar logs detalhados? (ex.: sim para ver cada etapa)", default=True)
    if verbose == "back":
        return "back"

    return RunOptions(
        ano=ano,
        mes=mes,
        data_inicio=data_inicio,
        data_fim=data_fim,
        verbose=bool(verbose),
    )


def _show_execution_preview(title: str, options: RunOptions) -> bool | str:
    preview = Table(title=title)
    preview.add_column("Parametro")
    preview.add_column("Valor")
    for key, value in options.to_kwargs().items():
        if value in (None, False):
            continue
        preview.add_row(key, str(value))
    if preview.row_count == 0:
        preview.add_row("execucao", "sem parametros")
    console.print(preview)
    return _prompt_yes_no("Confirmar execucao?", default=True)


def _build_real_migration_options() -> RunOptions | str:
    console.print("[bold]Migracao real Oracle -> PostgreSQL[/bold] [dim](ex.: --ano 2026 --verbose)[/dim]")
    options = _prompt_common_filters()
    if options == "back":
        return "back"
    return options


def _build_validation_options() -> RunOptions | str:
    console.print("[bold]Validacao pre-carga Oracle[/bold] [dim](ex.: --ano 2026 --validate-only --verbose)[/dim]")
    options = _prompt_common_filters()
    if options == "back":
        return "back"
    options.validate_only = True
    report_md = _prompt_yes_no("Gerar relatorio Markdown? (ex.: sim para salvar .md)", default=False)
    if report_md == "back":
        return "back"
    options.report_md = bool(report_md)
    return options


def _build_dry_run_options() -> RunOptions | str:
    console.print("[bold]Dry-run de migracao Oracle -> PostgreSQL[/bold] [dim](ex.: --ano 2026 --mes 1 --dry-run --verbose)[/dim]")
    options = _prompt_common_filters()
    if options == "back":
        return "back"
    options.dry_run = True
    return options


def _build_generate_cache_options() -> RunOptions | str:
    console.print("[bold]Geracao de cache JSON no PostgreSQL[/bold] [dim](ex.: --ano 2026 --mes 1 --generate-cache --verbose)[/dim]")
    options = _prompt_common_filters()
    if options == "back":
        return "back"
    options.generate_cache = True
    return options


def _build_refresh_cache_options() -> RunOptions | str:
    console.print("[bold]Refresh controlado do cache JSON[/bold] [dim](ex.: --generate-cache --refresh-cache-competencia)[/dim]")
    console.print("[1] Por competencia (ex.: ano 2026, mes 1)")
    console.print("[2] Por competencia + matricula (ex.: ano 2026, mes 1, matricula 123456)")
    console.print("[3] Por ano (ex.: ano 2026)")
    console.print("[0] Voltar")
    choice = _prompt_numeric_option("Selecione o escopo (ex.: 1):", {"0", "1", "2", "3"})
    if choice == "0":
        return "back"

    ano = _prompt_int("Ano (ex.: 2026)", min_value=1900, max_value=2999)
    if ano == "back":
        return "back"

    verbose = _prompt_yes_no("Ativar logs detalhados? (ex.: sim)", default=True)
    if verbose == "back":
        return "back"

    options = RunOptions(ano=ano, generate_cache=True, verbose=bool(verbose))

    if choice == "1":
        mes = _prompt_int("Mes (ex.: 1)", min_value=1, max_value=12)
        if mes == "back":
            return "back"
        options.mes = mes
        options.refresh_cache_competencia = True
        return options

    if choice == "2":
        mes = _prompt_int("Mes (ex.: 1)", min_value=1, max_value=12)
        if mes == "back":
            return "back"
        matricula = _prompt_text("Matricula (ex.: 123456)", required=True)
        if matricula == "back":
            return "back"
        options.mes = mes
        options.refresh_cache_matricula = matricula
        return options

    confirm = _prompt_yes_no(
        "Refresh anual remove e recria todo o cache do ano informado. Deseja continuar? (ex.: nao para cancelar)",
        default=False,
    )
    if confirm == "back":
        return "back"
    if not confirm:
        console.print("[yellow]Operacao cancelada.[/yellow]")
        return "back"
    options.refresh_cache_ano = True
    options.force_year_refresh = True
    return options


def _post_execution_menu() -> bool:
    console.print("\n[1] Voltar ao menu principal")
    console.print("[0] Encerrar aplicacao")
    choice = _prompt_numeric_option("Selecione uma opcao (ex.: 1):", {"0", "1"})
    return choice == "1"


def _pause_to_continue(message: str = "Pressione Enter para continuar...") -> None:
    console.input(f"\n{message}")


def _validate_run_request(options: RunOptions) -> None:
    ano = validate_year(options.ano)
    mes = validate_month(options.mes)
    data_inicio, data_fim = validate_date_range(options.data_inicio, options.data_fim, ano, mes)
    _resolve_cache_refresh_scope(
        generate_cache=options.generate_cache,
        month=mes,
        start_date=data_inicio,
        end_date=data_fim,
        refresh_cache_competencia=options.refresh_cache_competencia,
        refresh_cache_matricula=options.refresh_cache_matricula,
        refresh_cache_ano=options.refresh_cache_ano,
        force_year_refresh=options.force_year_refresh,
    )


def _execute_from_menu(title: str, options: RunOptions) -> bool:
    _clear_screen()
    try:
        _validate_run_request(options)
    except ValueError as exc:
        console.print(f"[bold red]Parametros invalidos para {title.lower()}:[/bold red] {exc}")
        _pause_to_continue("Pressione Enter para voltar ao menu principal...")
        return True

    confirm = _show_execution_preview(title, options)
    if confirm == "back":
        return True
    if not confirm:
        console.print("[yellow]Execucao cancelada antes do inicio.[/yellow]")
        return True

    exit_code = 0
    try:
        run(**options.to_kwargs())
        console.print("\n[bold green]Execucao concluida.[/bold green]")
    except typer.Exit as exc:
        exit_code = exc.exit_code or 0
        if exit_code == 0:
            console.print("\n[bold green]Execucao concluida.[/bold green]")
        else:
            console.print(f"\n[bold red]Execucao finalizada com falha (codigo {exit_code}).[/bold red]")
    return _post_execution_menu()


def start_interactive_menu() -> None:
    while True:
        _clear_screen()
        _print_menu_header(
            "Menu Principal",
            "Selecione a operacao desejada. Use o modo por flags quando precisar automatizar (ex.: python main.py --ano 2026 --verbose).",
        )
        console.print("[1] Migracao real Oracle -> PostgreSQL (ex.: ano 2026)")
        console.print("[2] Validacao pre-carga Oracle (ex.: ano 2026 com diagnostico)")
        console.print("[3] Dry-run de migracao Oracle -> PostgreSQL (ex.: ano 2026, mes 1)")
        console.print("[4] Gerar cache JSON no PostgreSQL (ex.: ano 2026, mes 1)")
        console.print("[5] Refresh controlado do cache JSON (ex.: competencia ou matricula)")
        console.print("[6] Ajuda (ex.: ver flags e comandos)")
        console.print("[7] Executar comando manual (ex.: --ano 2026 --dry-run)")
        console.print("[8] Gerar schema PostgreSQL normalizado (ex.: banco payroll_migration)")
        console.print("[0] Encerrar aplicacao")
        choice = _prompt_numeric_option("Selecione uma opcao (ex.: 4):", {"0", "1", "2", "3", "4", "5", "6", "7", "8"})

        if choice == "0":
            console.print("[bold cyan]Aplicacao encerrada.[/bold cyan]")
            return

        if choice == "6":
            _show_help_screen()
            continue
        if choice == "7":
            if not _execute_manual_command():
                console.print("[bold cyan]Aplicacao encerrada.[/bold cyan]")
                return
            continue
        if choice == "8":
            if not _run_schema_generation_menu():
                console.print("[bold cyan]Aplicacao encerrada.[/bold cyan]")
                return
            continue

        builder_map = {
            "1": ("Migracao real Oracle -> PostgreSQL", _build_real_migration_options),
            "2": ("Validacao pre-carga Oracle", _build_validation_options),
            "3": ("Dry-run de migracao Oracle -> PostgreSQL", _build_dry_run_options),
            "4": ("Geracao de cache JSON", _build_generate_cache_options),
            "5": ("Refresh controlado do cache JSON", _build_refresh_cache_options),
        }
        title, builder = builder_map[choice]
        _clear_screen()
        _print_menu_header(title, "Informe os parametros abaixo (exemplos visiveis em cada campo).")
        options = builder()
        if options == "back":
            continue
        if not _execute_from_menu(title, options):
            console.print("[bold cyan]Aplicacao encerrada.[/bold cyan]")
            return


def _resolve_cache_refresh_scope(
    generate_cache: bool,
    month: int | None,
    start_date: date | None,
    end_date: date | None,
    refresh_cache_competencia: bool,
    refresh_cache_matricula: str | None,
    refresh_cache_ano: bool,
    force_year_refresh: bool,
) -> tuple[str | None, str | None]:
    selected_scopes = sum(
        1
        for enabled in (
            refresh_cache_competencia,
            refresh_cache_matricula is not None,
            refresh_cache_ano,
        )
        if enabled
    )

    if selected_scopes and not generate_cache:
        raise ValueError("As flags de refresh de cache exigem o uso de --generate-cache.")

    if selected_scopes > 1:
        raise ValueError(
            "Use apenas uma entre --refresh-cache-competencia, --refresh-cache-matricula e --refresh-cache-ano."
        )

    if force_year_refresh and not refresh_cache_ano:
        raise ValueError("--force-year-refresh so pode ser usado em conjunto com --refresh-cache-ano.")

    if refresh_cache_ano:
        if not force_year_refresh:
            raise ValueError("Refresh anual exige --force-year-refresh para confirmacao explicita.")
        if month is not None:
            raise ValueError("Refresh anual nao aceita --mes.")
        if start_date is not None or end_date is not None:
            raise ValueError("Refresh anual nao aceita --data-inicio/--data-fim.")
        return "ano", None

    if refresh_cache_competencia:
        if month is None:
            raise ValueError("Refresh por competencia exige --mes.")
        if start_date is not None or end_date is not None:
            raise ValueError("Refresh por competencia nao aceita --data-inicio/--data-fim.")
        return "competencia", None

    if refresh_cache_matricula is not None:
        matricula = str(refresh_cache_matricula).strip()
        if not matricula:
            raise ValueError("Informe uma matricula valida em --refresh-cache-matricula.")
        if month is None:
            raise ValueError("Refresh por matricula exige --mes.")
        if start_date is not None or end_date is not None:
            raise ValueError("Refresh por matricula nao aceita --data-inicio/--data-fim.")
        return "matricula", matricula

    return None, None


def _finalize_failed_execution(
    *,
    ano: int,
    id_carga: int | None,
    postgres_engine,
    metadata,
    summary_counter: Counter,
    errors: list[dict[str, Any]],
    exc: Exception,
) -> None:
    if id_carga is None or postgres_engine is None or metadata is None:
        return

    errors.append(
        {
            "chave_origem": f"ANO={ano}",
            "mensagem_erro": str(exc),
            "payload_origem": {"ano": ano},
        }
    )
    registrar_erros(postgres_engine, metadata, id_carga, errors[-1:])
    finalizar_carga(
        postgres_engine,
        metadata,
        id_carga=id_carga,
        status="ERRO",
        qtd_lidos=summary_counter.get("folhas_oracle_lidas", 0) + summary_counter.get("linhas_brutas_oracle", 0),
        qtd_processados=summary_counter.get("contracheques_unicos_processados", 0) + summary_counter.get("itens_processados", 0),
        qtd_erros=len(errors),
        observacao=str(exc),
    )


def _run_validation_mode(
    ano: int,
    logger: logging.Logger,
    folhas_df: pd.DataFrame,
    contracheque_chunks,
    total_contracheques_origem: int,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    folhas_lookup_desc, folhas_lookup_mes = build_folha_lookup(folhas_df)
    folhas_analysis = analyze_folhas_por_mes(folhas_df)
    accumulator = ValidationAccumulator(folhas_lookup_desc, folhas_lookup_mes)
    processados = 0
    logger.info("Lendo contracheques em lotes de %s linhas.", VALIDATION_CHUNK_SIZE)
    with _build_progress() as progress:
        task_id = progress.add_task(
            "Validacao pre-carga em andamento",
            total=total_contracheques_origem if total_contracheques_origem > 0 else 1,
        )
        for idx, chunk in enumerate(contracheque_chunks, start=1):
            progress.update(task_id, description=f"Validacao pre-carga: transformando lote {idx}")
            servidores_df = transform_servidores(chunk)
            vinculos_df = transform_vinculos(chunk)
            rubricas_df = transform_rubricas(chunk)
            contracheques_df = transform_contracheques(chunk)
            itens_df = transform_itens(chunk)
            accumulator.consume(
                servidores_df=servidores_df,
                vinculos_df=vinculos_df,
                rubricas_df=rubricas_df,
                contracheques_df=contracheques_df,
                itens_df=itens_df,
            )
            processados += len(chunk)
            progress.update(
                task_id,
                advance=len(chunk),
                description=f"Validacao pre-carga: lote {idx} processado",
            )
            percentual = 0.0 if total_contracheques_origem == 0 else round((processados / total_contracheques_origem) * 100, 2)
            logger.info(
                "Validacao em andamento: lote %s processado (%s/%s linhas, %s%%).",
                idx,
                processados,
                total_contracheques_origem,
                percentual,
            )
        progress.update(task_id, completed=max(total_contracheques_origem, 1), description="Validacao pre-carga concluida")

    mapeamento_analysis, servidor_vinculo_analysis, rubrica_analysis, distribuicao_analysis = accumulator.finalize()

    render_validation_report(
        ano=ano,
        folhas_analysis=folhas_analysis,
        mapeamento_analysis=mapeamento_analysis,
        servidor_vinculo_analysis=servidor_vinculo_analysis,
        rubrica_analysis=rubrica_analysis,
        distribuicao_analysis=distribuicao_analysis,
    )
    return folhas_analysis, mapeamento_analysis, servidor_vinculo_analysis, rubrica_analysis, distribuicao_analysis


def _run_real_load_mode(
    logger: logging.Logger,
    postgres_engine,
    metadata,
    folhas_df: pd.DataFrame,
    contracheque_chunks,
    total_contracheques_origem: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    logger.info("Iniciando carga real em lotes de %s linhas brutas.", VALIDATION_CHUNK_SIZE)

    unique_servidores: set[int] = set()
    unique_vinculos: set[tuple[int, int]] = set()
    unique_rubricas: set[int] = set()
    unique_contracheques: set[tuple[int, int, date, int]] = set()
    total_snapshots = 0
    total_itens_processados = 0
    total_itens_inseridos = 0
    total_divergencias = 0
    total_linhas_brutas = 0
    errors: list[dict[str, Any]] = []

    with postgres_engine.begin() as connection:
        logger.info("Carga real: carregando folha_referencia.")
        load_folhas(connection, metadata, folhas_df)
        folha_map = fetch_folha_map(connection, metadata, folhas_df)
    folha_desc_map, folha_mes_unica_map = _build_folha_desc_map(folhas_df, folha_map)
    logger.info("Carga real: folha_referencia concluida (%s registros).", len(folhas_df))

    with _build_progress() as progress:
        task_id = progress.add_task(
            "Carga real em andamento",
            total=total_contracheques_origem if total_contracheques_origem > 0 else 1,
        )
        for idx, chunk in enumerate(contracheque_chunks, start=1):
            chunk_size = len(chunk)
            total_linhas_brutas += chunk_size
            percentual = 0.0 if total_contracheques_origem == 0 else round((total_linhas_brutas / total_contracheques_origem) * 100, 2)
            logger.info(
                "Chunk %s iniciado: %s linhas brutas (%s/%s, %s%%).",
                idx,
                chunk_size,
                total_linhas_brutas,
                total_contracheques_origem,
                percentual,
            )
            progress.update(task_id, description=f"Carga real: transformando lote {idx}")
            logger.info("Chunk %s: transformando dados.", idx)

            servidores_df = transform_servidores(chunk)
            vinculos_df = transform_vinculos(chunk)
            rubricas_df = transform_rubricas(chunk)
            contracheques_df = transform_contracheques(chunk)
            snapshots_df = transform_snapshots(chunk)
            itens_df = transform_itens(chunk)

            unique_servidores.update(int(value) for value in servidores_df["numfunc"].dropna().tolist())
            unique_vinculos.update((int(row.numfunc), int(row.numvinc)) for row in vinculos_df.itertuples())
            unique_rubricas.update(int(value) for value in rubricas_df["codigo_rubrica"].dropna().tolist())
            unique_contracheques.update(
                (int(row.numfunc), int(row.numvinc), row.mes_ano, int(row.numero))
                for row in contracheques_df.itertuples()
            )
            total_snapshots += len(snapshots_df)
            total_itens_processados += len(itens_df)

            progress.update(task_id, description=f"Carga real: persistindo lote {idx}")
            with postgres_engine.begin() as connection:
                logger.info("Chunk %s: carregando servidor.", idx)
                load_servidores(connection, metadata, servidores_df)
                servidor_map = fetch_servidor_map(connection, metadata, servidores_df["numfunc"].tolist())

                vinculos_enriched = _add_servidor_ids(vinculos_df, servidor_map)
                vinculos_prepared, vinculo_errors = prepare_vinculos(vinculos_enriched, servidor_map)
                errors.extend(vinculo_errors)
                logger.info("Chunk %s: carregando servidor_vinculo.", idx)
                load_vinculos(connection, metadata, vinculos_prepared)
                vinculo_map = fetch_vinculo_map(connection, metadata, vinculos_prepared)

                logger.info("Chunk %s: carregando rubrica.", idx)
                load_rubricas(connection, metadata, rubricas_df)
                rubrica_map = fetch_rubrica_map(connection, metadata, rubricas_df["codigo_rubrica"].tolist())

                contracheques_enriched = _add_servidor_ids(contracheques_df, servidor_map)
                contracheques_prepared, contracheque_errors = prepare_contracheques(
                    contracheques_enriched,
                    vinculo_map,
                    folha_desc_map,
                    folha_mes_unica_map,
                )
                errors.extend(contracheque_errors)
                logger.info("Chunk %s: carregando contracheque.", idx)
                load_contracheques(connection, metadata, contracheques_prepared)
                contracheque_map = fetch_contracheque_map(connection, metadata, contracheques_prepared)

                snapshots_enriched = _add_servidor_ids(snapshots_df, servidor_map)
                snapshots_prepared, snapshot_errors = prepare_snapshots(snapshots_enriched, vinculo_map, contracheque_map)
                errors.extend(snapshot_errors)
                logger.info("Chunk %s: carregando contracheque_snapshot_funcional.", idx)
                load_snapshots(connection, metadata, snapshots_prepared)

                itens_enriched = _add_servidor_ids(itens_df, servidor_map)
                itens_prepared, item_errors = prepare_itens(itens_enriched, vinculo_map, contracheque_map, rubrica_map)
                errors.extend(item_errors)
                logger.info("Chunk %s: carregando contracheque_item.", idx)
                item_stats = load_itens(connection, metadata, itens_prepared)
                total_itens_inseridos += item_stats["processados"]

                consolidados_df = prepare_consolidados(contracheques_prepared, itens_prepared, contracheque_map)
                logger.info("Chunk %s: carregando contracheque_consolidado.", idx)
                load_consolidados(connection, metadata, consolidados_df)

                if not consolidados_df.empty:
                    divergencias = (
                        (consolidados_df["divergencia_bruto"].astype(str) != "0.00")
                        | (consolidados_df["divergencia_descontos"].astype(str) != "0.00")
                        | (consolidados_df["divergencia_liquido"].astype(str) != "0.00")
                    )
                    total_divergencias += int(divergencias.sum())

            progress.update(task_id, advance=chunk_size, description=f"Carga real: lote {idx} concluido")
            logger.info(
                "Chunk %s concluido: servidores=%s, vinculos=%s, rubricas=%s, contracheques=%s, itens_inseridos=%s, erros_acumulados=%s.",
                idx,
                len(servidores_df),
                len(vinculos_df),
                len(rubricas_df),
                len(contracheques_df),
                item_stats["processados"],
                len(errors),
            )
        progress.update(task_id, completed=max(total_contracheques_origem, 1), description="Carga real concluida")

    return (
        {
            "linhas_brutas_oracle": total_linhas_brutas,
            "servidores_unicos": len(unique_servidores),
            "vinculos_unicos": len(unique_vinculos),
            "rubricas_unicas": len(unique_rubricas),
            "contracheques_unicos_processados": len(unique_contracheques),
            "snapshots_processados": total_snapshots,
            "itens_processados": total_itens_processados,
            "itens_inseridos": total_itens_inseridos,
            "divergencias_encontradas": total_divergencias,
        },
        errors,
    )


def _run_cache_mode(
    logger: logging.Logger,
    postgres_engine,
    metadata,
    year: int,
    month: int | None,
    start_date: date | None,
    end_date: date | None,
    cache_matricula: str | None,
    refresh_scope: str | None,
) -> dict[str, Any]:
    logger.info("Modo cache JSON: lendo dados normalizados do PostgreSQL.")
    total_candidatos = 0
    total_cache_removidos = 0
    total_cache_processados = 0
    total_cache_inserts = 0
    total_cache_updates = 0
    total_rubricas = 0
    offset = 0
    batch_index = 0

    if refresh_scope is not None:
        with console.status("[bold cyan]Aplicando limpeza previa do cache JSON...[/bold cyan]", spinner="dots"):
            with postgres_engine.begin() as connection:
                if refresh_scope == "competencia":
                    logger.info("Limpando cache por competencia: ano=%s, mes=%s", year, month)
                    total_cache_removidos = delete_contracheque_cache(connection, metadata, year=year, month=month)
                elif refresh_scope == "matricula":
                    logger.info(
                        "Limpando cache por matricula: ano=%s, mes=%s, matricula=%s",
                        year,
                        month,
                        cache_matricula,
                    )
                    total_cache_removidos = delete_contracheque_cache(
                        connection,
                        metadata,
                        year=year,
                        month=month,
                        matricula=cache_matricula,
                    )
                elif refresh_scope == "ano":
                    logger.info("Limpando cache por ano: ano=%s", year)
                    total_cache_removidos = delete_contracheque_cache(connection, metadata, year=year)
                logger.info("Cache JSON: registros removidos no refresh=%s", total_cache_removidos)

    with console.status("[bold cyan]Contando contracheques elegiveis para cache JSON...[/bold cyan]", spinner="dots"):
        with postgres_engine.connect() as connection:
            total_candidatos = count_cache_candidates(connection, year, month, start_date, end_date, cache_matricula)
    if cache_matricula is not None:
        logger.info("Cache JSON: filtrando geracao para matricula=%s", cache_matricula)
    logger.info("Cache JSON: %s contracheques elegiveis para processamento.", total_candidatos)

    with _build_progress() as progress:
        task_id = progress.add_task(
            "Geracao de cache JSON em andamento",
            total=total_candidatos if total_candidatos > 0 else 1,
        )
        while offset < total_candidatos:
            batch_index += 1
            progress.update(task_id, description=f"Cache JSON: carregando lote {batch_index}")
            with postgres_engine.connect() as connection:
                candidates_df = load_cache_candidates(
                    connection,
                    year=year,
                    month=month,
                    start_date=start_date,
                    end_date=end_date,
                    matricula=cache_matricula,
                    offset=offset,
                    limit=CACHE_BATCH_SIZE,
                )
                if candidates_df.empty:
                    break
                items_df = load_cache_items(connection, candidates_df["id_contracheque"].astype(int).tolist())

            logger.info(
                "Cache JSON: lote %s carregado (%s candidatos, offset=%s).",
                batch_index,
                len(candidates_df),
                offset,
            )
            progress.update(task_id, description=f"Cache JSON: montando payload do lote {batch_index}")
            payloads = build_cache_payloads(candidates_df, items_df)
            total_rubricas += sum(len(row["contracheque_json"]["rubricas"]) for row in payloads)
            exemplos = [
                (
                    row["matricula"],
                    row["ano"],
                    row["mes"],
                    row["folha_numero"],
                    row["folha_descricao"],
                )
                for row in payloads[:3]
            ]
            logger.info(
                "Cache JSON: lote %s gerou %s JSONs e %s rubricas. Exemplos: %s",
                batch_index,
                len(payloads),
                sum(len(row["contracheque_json"]["rubricas"]) for row in payloads),
                exemplos,
            )

            progress.update(task_id, description=f"Cache JSON: persistindo lote {batch_index}")
            with postgres_engine.begin() as connection:
                persist_summary = load_contracheque_cache(connection, metadata, payloads)
                total_cache_processados += persist_summary["processados"]
                total_cache_inserts += persist_summary["inseridos"]
                total_cache_updates += persist_summary["atualizados"]

            offset += len(candidates_df)
            progress.update(task_id, advance=len(candidates_df), description=f"Cache JSON: lote {batch_index} concluido")
            percentual = 0.0 if total_candidatos == 0 else round((offset / total_candidatos) * 100, 2)
            logger.info(
                "Cache JSON: lote %s persistido (%s/%s, %s%%). Inseridos=%s Atualizados=%s.",
                batch_index,
                offset,
                total_candidatos,
                percentual,
                persist_summary["inseridos"],
                persist_summary["atualizados"],
            )
        progress.update(task_id, completed=max(total_candidatos, 1), description="Geracao de cache JSON concluida")

    return {
        "cache_removidos": total_cache_removidos,
        "contracheques_elegiveis_cache": total_candidatos,
        "cache_processados": total_cache_processados,
        "cache_inseridos": total_cache_inserts,
        "cache_atualizados": total_cache_updates,
        "rubricas_cache": total_rubricas,
    }


def run(
    ano: int = typer.Option(..., "--ano", help="Ano a ser processado."),
    mes: int | None = typer.Option(None, "--mes", help="Mes a ser processado (1-12)."),
    data_inicio: str | None = typer.Option(None, "--data-inicio", help="Data inicial opcional no formato YYYY-MM-DD."),
    data_fim: str | None = typer.Option(None, "--data-fim", help="Data final opcional no formato YYYY-MM-DD."),
    generate_cache: bool = typer.Option(False, "--generate-cache", help="Gera e persiste o JSON mensal em contracheque_cache."),
    refresh_cache_competencia: bool = typer.Option(
        False,
        "--refresh-cache-competencia",
        help="Apaga previamente o cache da competencia (ano+mes) antes de regenerar.",
    ),
    refresh_cache_matricula: str | None = typer.Option(
        None,
        "--refresh-cache-matricula",
        help="Apaga previamente o cache de uma matricula na competencia informada (ano+mes+matricula).",
    ),
    refresh_cache_ano: bool = typer.Option(
        False,
        "--refresh-cache-ano",
        help="Apaga previamente todo o cache do ano informado antes de regenerar.",
    ),
    force_year_refresh: bool = typer.Option(
        False,
        "--force-year-refresh",
        help="Confirma explicitamente o refresh anual do cache. Obrigatorio com --refresh-cache-ano.",
    ),
    report_md: bool = typer.Option(False, "--report-md", help="Gera relatorio .md na raiz do projeto."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Executa extracao e transformacao sem gravar."),
    validate_only: bool = typer.Option(False, "--validate-only", help="Executa apenas diagnostico sem gravar e sem conectar ao PostgreSQL."),
    verbose: bool = typer.Option(False, "--verbose", help="Exibe logs detalhados."),
) -> None:
    logger = setup_logger(verbose=verbose)
    start_time = time.perf_counter()
    summary_counter = Counter()
    errors: list[dict[str, Any]] = []
    id_carga: int | None = None
    postgres_engine = None
    metadata = None
    validation_payload = None

    try:
        ano = validate_year(ano)
        mes = validate_month(mes)
        data_inicio, data_fim = validate_date_range(data_inicio, data_fim, ano, mes)
        cache_refresh_scope, cache_matricula = _resolve_cache_refresh_scope(
            generate_cache=generate_cache,
            month=mes,
            start_date=data_inicio,
            end_date=data_fim,
            refresh_cache_competencia=refresh_cache_competencia,
            refresh_cache_matricula=refresh_cache_matricula,
            refresh_cache_ano=refresh_cache_ano,
            force_year_refresh=force_year_refresh,
        )
        settings = load_settings()

        logger.info("Iniciando ETL de contracheques.")
        logger.info("Ano processado: %s", ano)
        logger.info("Mes processado: %s", mes if mes is not None else "TODOS")
        logger.info(
            "Intervalo de datas: %s",
            f"{data_inicio} ate {data_fim}" if data_inicio and data_fim else "PADRAO",
        )
        logger.info("Modo generate-cache: %s", "SIM" if generate_cache else "NAO")
        logger.info("Refresh cache por competencia: %s", "SIM" if refresh_cache_competencia else "NAO")
        logger.info("Refresh cache por matricula: %s", cache_matricula or "NAO")
        logger.info("Refresh cache por ano: %s", "SIM" if refresh_cache_ano else "NAO")
        logger.info("Modo dry-run: %s", "SIM" if dry_run else "NAO")
        logger.info("Modo validate-only: %s", "SIM" if validate_only else "NAO")

        if generate_cache:
            postgres_engine = _run_with_status(
                "Conectando ao PostgreSQL para geracao de cache JSON...",
                create_postgres_engine,
                settings,
            )
            metadata = _run_with_status(
                "Refletindo metadata do PostgreSQL...",
                reflect_metadata,
                postgres_engine,
            )
            cache_summary = _run_cache_mode(
                logger=logger,
                postgres_engine=postgres_engine,
                metadata=metadata,
                year=ano,
                month=mes,
                start_date=data_inicio,
                end_date=data_fim,
                cache_matricula=cache_matricula,
                refresh_scope=cache_refresh_scope,
            )
            elapsed = time.perf_counter() - start_time
            summary_counter.update(cache_summary)
            summary_counter["tempo_total_segundos"] = f"{elapsed:.2f}"
            console.print(_summary_table(dict(summary_counter)))
            return

        oracle_engine = _run_with_status(
            "Conectando ao Oracle de origem...",
            create_oracle_engine,
            settings,
        )

        with oracle_engine.connect() as oracle_conn:
            _run_with_status(
                "Inicializando sessao Oracle...",
                initialize_oracle_session,
                oracle_conn,
            )
            folhas_source = _run_with_status(
                "Resolvendo origem Oracle de folhas...",
                resolve_oracle_object_name,
                oracle_conn,
                "PAYROLL_FOLHAS_VIEW",
                settings.oracle_source_schema,
            )
            contracheque_source = _run_with_status(
                "Resolvendo origem Oracle de contracheques...",
                resolve_oracle_object_name,
                oracle_conn,
                "PAYROLL_CHECKS_VIEW",
                settings.oracle_source_schema,
            )
            logger.info("Origem Oracle folhas: %s", folhas_source)
            logger.info("Origem Oracle contracheque: %s", contracheque_source)
            total_folhas_origem = _run_with_status(
                "Contando registros de folhas no Oracle...",
                count_folhas,
                oracle_conn,
                ano,
                folhas_source,
                mes,
                data_inicio,
                data_fim,
            )
            total_contracheques_origem = _run_with_status(
                "Contando contracheques no Oracle...",
                count_contracheques,
                oracle_conn,
                ano,
                contracheque_source,
                mes,
                data_inicio,
                data_fim,
            )
            logger.info("Contagem Oracle folhas: %s", total_folhas_origem)
            logger.info("Contagem Oracle contracheques: %s", total_contracheques_origem)
            folhas_raw = _run_with_status(
                "Extraindo folhas do Oracle...",
                extract_folhas,
                oracle_conn,
                ano,
                folhas_source,
                mes,
                data_inicio,
                data_fim,
            )

            if validate_only:
                folhas_df = _run_with_status(
                    "Transformando folhas para validacao pre-carga...",
                    transform_folhas,
                    folhas_raw,
                )
                summary_counter["folhas_oracle_lidas"] = len(folhas_raw)
                summary_counter["linhas_brutas_oracle"] = total_contracheques_origem
                summary_counter["divergencias_encontradas"] = 0
                summary_counter["itens_inseridos"] = 0
                summary_counter["contracheques_unicos_processados"] = 0
                logger.info("Folhas extraidas: %s", len(folhas_raw))
                logger.info("Executando validacao pre-carga sem conexao com PostgreSQL.")
                contracheque_chunks = iter_contracheques(
                    oracle_conn,
                    ano,
                    contracheque_source,
                    mes,
                    data_inicio,
                    data_fim,
                    chunk_size=VALIDATION_CHUNK_SIZE,
                )
                validation_payload = _run_validation_mode(
                    ano=ano,
                    logger=logger,
                    folhas_df=folhas_df,
                    contracheque_chunks=contracheque_chunks,
                    total_contracheques_origem=total_contracheques_origem,
                )
                _, mapeamento_analysis, servidor_vinculo_analysis, rubrica_analysis, distribuicao_analysis = validation_payload
                summary_counter["contracheques_unicos_processados"] = mapeamento_analysis["total_contracheques"]
                summary_counter["servidores_unicos"] = servidor_vinculo_analysis["servidores_unicos"]
                summary_counter["vinculos_unicos"] = servidor_vinculo_analysis["vinculos_unicos"]
                summary_counter["rubricas_unicas"] = rubrica_analysis["rubricas_distintas"]
                summary_counter["media_itens_por_contracheque"] = f"{distribuicao_analysis['media_itens_por_contracheque']:.2f}"
                elapsed = time.perf_counter() - start_time
                summary_counter["erros"] = 0
                summary_counter["tempo_total_segundos"] = f"{elapsed:.2f}"
                if report_md and validation_payload is not None:
                    report_path = _run_with_status(
                        "Gerando relatorio Markdown da validacao...",
                        write_validation_report_markdown,
                        output_path=_build_report_path(ano, mes, data_inicio, data_fim),
                        ano=ano,
                        folhas_analysis=validation_payload[0],
                        mapeamento_analysis=validation_payload[1],
                        servidor_vinculo_analysis=validation_payload[2],
                        rubrica_analysis=validation_payload[3],
                        distribuicao_analysis=validation_payload[4],
                        summary=dict(summary_counter),
                    )
                    logger.info("Relatorio Markdown gerado em: %s", report_path)
                    summary_counter["relatorio_md"] = report_path.name
                console.print(_summary_table(dict(summary_counter)))
                return
            folhas_df = _run_with_status(
                "Transformando folhas para processamento...",
                transform_folhas,
                folhas_raw,
            )
            summary_counter["folhas_oracle_lidas"] = len(folhas_raw)
            summary_counter["linhas_brutas_oracle"] = total_contracheques_origem
            summary_counter["divergencias_encontradas"] = 0
            summary_counter["itens_inseridos"] = 0

            if dry_run:
                logger.info("Modo dry-run: extraindo conjunto completo para transformacao sem gravacao.")
                contracheques_raw = _run_with_status(
                    "Extraindo contracheques do Oracle para dry-run...",
                    extract_contracheques,
                    oracle_conn,
                    ano,
                    contracheque_source,
                    mes,
                    data_inicio,
                    data_fim,
                )
                _log_counts(logger, folhas_raw, contracheques_raw)
                with _build_progress() as progress:
                    task_id = progress.add_task("Dry-run: transformando dados", total=6)
                    progress.update(task_id, description="Dry-run: transformando servidores")
                    servidores_df = transform_servidores(contracheques_raw)
                    progress.advance(task_id)
                    progress.update(task_id, description="Dry-run: transformando vinculos")
                    vinculos_df = transform_vinculos(contracheques_raw)
                    progress.advance(task_id)
                    progress.update(task_id, description="Dry-run: transformando rubricas")
                    rubricas_df = transform_rubricas(contracheques_raw)
                    progress.advance(task_id)
                    progress.update(task_id, description="Dry-run: transformando contracheques")
                    contracheques_df = transform_contracheques(contracheques_raw)
                    progress.advance(task_id)
                    progress.update(task_id, description="Dry-run: transformando snapshots")
                    snapshots_df = transform_snapshots(contracheques_raw)
                    progress.advance(task_id)
                    progress.update(task_id, description="Dry-run: transformando itens")
                    itens_df = transform_itens(contracheques_raw)
                    progress.advance(task_id)
                    progress.update(task_id, description="Dry-run concluido", completed=6)

                summary_counter["servidores_unicos"] = len(servidores_df)
                summary_counter["vinculos_unicos"] = len(vinculos_df)
                summary_counter["rubricas_unicas"] = len(rubricas_df)
                summary_counter["contracheques_unicos_processados"] = len(contracheques_df)
                summary_counter["snapshots_processados"] = len(snapshots_df)
                summary_counter["itens_processados"] = len(itens_df)
                logger.info("Dry-run finalizado sem gravacao no PostgreSQL.")
            else:
                postgres_engine = _run_with_status(
                    "Conectando ao PostgreSQL de destino...",
                    create_postgres_engine,
                    settings,
                )
                metadata = _run_with_status(
                    "Refletindo metadata do PostgreSQL de destino...",
                    reflect_metadata,
                    postgres_engine,
                )
                id_carga = iniciar_carga(postgres_engine, metadata, "ORACLE", f"ANO={ano}")
                logger.info("Registro de carga criado em carga_importacao com id %s.", id_carga)

                contracheque_chunks = iter_contracheques(
                    oracle_conn,
                    ano,
                    contracheque_source,
                    mes,
                    data_inicio,
                    data_fim,
                    chunk_size=VALIDATION_CHUNK_SIZE,
                )
                load_summary, errors = _run_real_load_mode(
                    logger=logger,
                    postgres_engine=postgres_engine,
                    metadata=metadata,
                    folhas_df=folhas_df,
                    contracheque_chunks=contracheque_chunks,
                    total_contracheques_origem=total_contracheques_origem,
                )
                summary_counter.update(load_summary)

                if errors:
                    logger.warning("Carga real concluida com %s erros de preparo/mapeamento.", len(errors))
                    registrar_erros(postgres_engine, metadata, id_carga, errors)

        elapsed = time.perf_counter() - start_time
        summary_counter["erros"] = len(errors)
        summary_counter["tempo_total_segundos"] = f"{elapsed:.2f}"

        if id_carga is not None:
            finalizar_carga(
                postgres_engine,
                metadata,
                id_carga=id_carga,
                status="SUCESSO" if not errors else "SUCESSO_PARCIAL",
                qtd_lidos=summary_counter["folhas_oracle_lidas"] + summary_counter["linhas_brutas_oracle"],
                qtd_processados=summary_counter["contracheques_unicos_processados"] + summary_counter["itens_processados"],
                qtd_erros=len(errors),
                observacao="Execucao concluida pela CLI Python.",
            )

        console.print(_summary_table(dict(summary_counter)))
    except ValueError as exc:
        logger.error("Falha de validacao do ETL: %s", exc)
        _finalize_failed_execution(
            ano=ano,
            id_carga=id_carga,
            postgres_engine=postgres_engine,
            metadata=metadata,
            summary_counter=summary_counter,
            errors=errors,
            exc=exc,
        )
        console.print(f"\n[bold red]Erro de validacao:[/bold red] {exc}")
        raise typer.Exit(code=2) from exc
    except Exception as exc:
        logger.exception("Falha durante a execucao do ETL: %s", exc)
        _finalize_failed_execution(
            ano=ano,
            id_carga=id_carga,
            postgres_engine=postgres_engine,
            metadata=metadata,
            summary_counter=summary_counter,
            errors=errors,
            exc=exc,
        )
        console.print(f"\n[bold red]Falha inesperada durante a execucao do ETL:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc


app.command()(run)


def _build_report_path(ano: int, mes: int | None, data_inicio: date | None, data_fim: date | None) -> str:
    suffix_parts = [str(ano)]
    if mes is not None:
        suffix_parts.append(f"mes_{mes:02d}")
    if data_inicio and data_fim:
        suffix_parts.append(f"{data_inicio.isoformat()}_{data_fim.isoformat()}")
    suffix = "_".join(suffix_parts)
    return str(Path.cwd() / f"validation_report_{suffix}.md")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        app()
    else:
        start_interactive_menu()
