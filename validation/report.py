from __future__ import annotations

from pathlib import Path
from typing import Any

from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from utils.logger import console


def render_validation_report(
    ano: int,
    folhas_analysis: dict[str, Any],
    mapeamento_analysis: dict[str, Any],
    servidor_vinculo_analysis: dict[str, Any],
    rubrica_analysis: dict[str, Any],
    distribuicao_analysis: dict[str, Any],
) -> None:
    console.print(Panel.fit(f"Diagnostico Oracle Pre-Carga | Ano {ano}", style="bold cyan"))
    console.print(_status_panel(mapeamento_analysis, rubrica_analysis))
    console.print(_folhas_table(folhas_analysis))
    console.print(_mapeamento_table(mapeamento_analysis))
    console.print(_servidor_vinculo_table(servidor_vinculo_analysis))
    console.print(_rubrica_table(rubrica_analysis))
    console.print(_distribuicao_table(distribuicao_analysis))

    if folhas_analysis["meses_multiplos"]:
        console.print(_meses_multiplos_table(folhas_analysis["meses_multiplos"]))
    if mapeamento_analysis["exemplos_falha"]:
        console.print(_falhas_table("Falhas de mapeamento de folha", mapeamento_analysis["exemplos_falha"]))
    if servidor_vinculo_analysis["exemplos_sem_vinculo"]:
        console.print(_falhas_table("Contracheques sem vinculo valido", servidor_vinculo_analysis["exemplos_sem_vinculo"]))
    if rubrica_analysis["exemplos_rubrica_nula"]:
        console.print(_falhas_table("Exemplos de rubrica nula", rubrica_analysis["exemplos_rubrica_nula"]))


def write_validation_report_markdown(
    output_path: str | Path,
    ano: int,
    folhas_analysis: dict[str, Any],
    mapeamento_analysis: dict[str, Any],
    servidor_vinculo_analysis: dict[str, Any],
    rubrica_analysis: dict[str, Any],
    distribuicao_analysis: dict[str, Any],
    summary: dict[str, Any],
) -> Path:
    path = Path(output_path)
    mapeamento_status = "OK"
    if mapeamento_analysis["nao_mapeados"] != 0:
        mapeamento_status = f"Falhas encontradas ({mapeamento_analysis['nao_mapeados']})"
    content = [
        f"# Diagnostico Oracle Pre-Carga - Ano {ano}",
        "",
        "## Alertas",
        "",
        f"- Mapeamento: {mapeamento_status}",
        f"- Taxa de fallback: {mapeamento_analysis['taxa_fallback']}%",
        f"- Rubricas consistentes: {'sim' if rubrica_analysis['rubricas_nulas'] == 0 and rubrica_analysis['nomes_rubrica_vazios'] == 0 else 'nao'}",
        "",
        "## Analise de Folhas por Mes",
        "",
        _markdown_kv_table(
            [
                ("Total de meses", folhas_analysis["total_meses"]),
                ("Meses com folha unica", folhas_analysis["meses_folha_unica"]),
                ("Meses com multiplas folhas", folhas_analysis["meses_multiplas_folhas"]),
            ]
        ),
        "",
        "## Mapeamento Contracheque -> Folha",
        "",
        _markdown_kv_table(
            [
                ("Total de contracheques", mapeamento_analysis["total_contracheques"]),
                ("Mapeados por descricao", mapeamento_analysis["mapeados_por_descricao"]),
                ("Mapeados por fallback", mapeamento_analysis["mapeados_por_fallback"]),
                ("Nao mapeados", mapeamento_analysis["nao_mapeados"]),
                ("Taxa de sucesso", f"{mapeamento_analysis['taxa_sucesso']}%"),
                ("Taxa de fallback", f"{mapeamento_analysis['taxa_fallback']}%"),
                ("Taxa de erro", f"{mapeamento_analysis['taxa_erro']}%"),
            ]
        ),
        "",
        "## Analise de Servidor e Vinculo",
        "",
        _markdown_kv_table(
            [
                ("Servidores unicos", servidor_vinculo_analysis["servidores_unicos"]),
                ("Vinculos unicos", servidor_vinculo_analysis["vinculos_unicos"]),
                ("Contracheques sem vinculo valido", servidor_vinculo_analysis["contracheques_sem_vinculo"]),
            ]
        ),
        "",
        "## Analise de Rubricas",
        "",
        _markdown_kv_table(
            [
                ("Rubricas distintas", rubrica_analysis["rubricas_distintas"]),
                ("Rubrica nula", rubrica_analysis["rubricas_nulas"]),
                ("Nome de rubrica vazio", rubrica_analysis["nomes_rubrica_vazios"]),
            ]
        ),
        "",
        "## Distribuicao",
        "",
        "| Mes | Contracheques |",
        "| --- | ---: |",
    ]

    for row in distribuicao_analysis["contracheques_por_mes"]:
        content.append(f"| {row['mes_ano']} | {row['quantidade']} |")

    content.extend(
        [
            "",
            f"Media de itens por contracheque: {distribuicao_analysis['media_itens_por_contracheque']:.2f}",
            "",
            "## Resumo da Execucao",
            "",
            _markdown_kv_table(list(summary.items())),
        ]
    )

    if folhas_analysis["meses_multiplos"]:
        content.extend(["", "## Meses com Multiplas Folhas", "", _markdown_rows_table(folhas_analysis["meses_multiplos"])])
    if mapeamento_analysis["exemplos_falha"]:
        content.extend(["", "## Falhas de Mapeamento de Folha", "", _markdown_rows_table(mapeamento_analysis["exemplos_falha"])])
    if servidor_vinculo_analysis["exemplos_sem_vinculo"]:
        content.extend(["", "## Contracheques sem Vinculo Valido", "", _markdown_rows_table(servidor_vinculo_analysis["exemplos_sem_vinculo"])])
    if rubrica_analysis["exemplos_rubrica_nula"]:
        content.extend(["", "## Exemplos de Rubrica Nula", "", _markdown_rows_table(rubrica_analysis["exemplos_rubrica_nula"])])

    path.write_text("\n".join(content) + "\n", encoding="utf-8")
    return path


def _markdown_kv_table(rows: list[tuple[str, Any]]) -> str:
    lines = ["| Metrica | Valor |", "| --- | ---: |"]
    for key, value in rows:
        lines.append(f"| {key} | {value} |")
    return "\n".join(lines)


def _markdown_rows_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "_Sem registros_"
    headers = list(rows[0].keys())
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        values = []
        for header in headers:
            value = row.get(header, "")
            if isinstance(value, list):
                value = ", ".join(str(item) for item in value)
            values.append(str(value))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def _status_panel(mapeamento_analysis: dict[str, Any], rubrica_analysis: dict[str, Any]) -> Panel:
    linhas = []
    if mapeamento_analysis["nao_mapeados"] == 0:
        linhas.append("[green]✔ mapeamento OK[/green]")
    else:
        linhas.append(f"[red]❌ falhas encontradas: {mapeamento_analysis['nao_mapeados']}[/red]")

    if mapeamento_analysis["taxa_fallback"] >= 10:
        linhas.append(f"[yellow]⚠ fallback alto: {mapeamento_analysis['taxa_fallback']}%[/yellow]")
    else:
        linhas.append(f"[green]✔ fallback sob controle: {mapeamento_analysis['taxa_fallback']}%[/green]")

    if rubrica_analysis["rubricas_nulas"] > 0 or rubrica_analysis["nomes_rubrica_vazios"] > 0:
        linhas.append(
            f"[yellow]⚠ inconsistencias de rubrica: nulas={rubrica_analysis['rubricas_nulas']}, nomes_vazios={rubrica_analysis['nomes_rubrica_vazios']}[/yellow]"
        )
    else:
        linhas.append("[green]✔ rubricas consistentes[/green]")

    return Panel(Text.from_markup("\n".join(linhas)), title="Alertas", border_style="white")


def _folhas_table(analysis: dict[str, Any]) -> Table:
    table = Table(title="Analise de Folhas por Mes")
    table.add_column("Metrica")
    table.add_column("Valor", justify="right")
    table.add_row("Total de meses", str(analysis["total_meses"]))
    table.add_row("Meses com folha unica", str(analysis["meses_folha_unica"]))
    table.add_row("Meses com multiplas folhas", str(analysis["meses_multiplas_folhas"]))
    return table


def _mapeamento_table(analysis: dict[str, Any]) -> Table:
    table = Table(title="Mapeamento Contracheque -> Folha")
    table.add_column("Metrica")
    table.add_column("Valor", justify="right")
    table.add_row("Total de contracheques", str(analysis["total_contracheques"]))
    table.add_row("Mapeados por descricao", str(analysis["mapeados_por_descricao"]))
    table.add_row("Mapeados por fallback", str(analysis["mapeados_por_fallback"]))
    table.add_row("Nao mapeados", str(analysis["nao_mapeados"]))
    table.add_row("Taxa de sucesso", f"{analysis['taxa_sucesso']}%")
    table.add_row("Taxa de fallback", f"{analysis['taxa_fallback']}%")
    table.add_row("Taxa de erro", f"{analysis['taxa_erro']}%")
    return table


def _servidor_vinculo_table(analysis: dict[str, Any]) -> Table:
    table = Table(title="Analise de Servidor e Vinculo")
    table.add_column("Metrica")
    table.add_column("Valor", justify="right")
    table.add_row("Servidores unicos", str(analysis["servidores_unicos"]))
    table.add_row("Vinculos unicos", str(analysis["vinculos_unicos"]))
    table.add_row("Contracheques sem vinculo valido", str(analysis["contracheques_sem_vinculo"]))
    return table


def _rubrica_table(analysis: dict[str, Any]) -> Table:
    table = Table(title="Analise de Rubricas")
    table.add_column("Metrica")
    table.add_column("Valor", justify="right")
    table.add_row("Rubricas distintas", str(analysis["rubricas_distintas"]))
    table.add_row("Rubrica nula", str(analysis["rubricas_nulas"]))
    table.add_row("Nome de rubrica vazio", str(analysis["nomes_rubrica_vazios"]))
    return table


def _distribuicao_table(analysis: dict[str, Any]) -> Table:
    table = Table(title="Distribuicao")
    table.add_column("Mes")
    table.add_column("Contracheques", justify="right")
    for row in analysis["contracheques_por_mes"]:
        table.add_row(str(row["mes_ano"]), str(row["quantidade"]))
    table.caption = f"Media de itens por contracheque: {analysis['media_itens_por_contracheque']:.2f}"
    return table


def _meses_multiplos_table(rows: list[dict[str, Any]]) -> Table:
    table = Table(title="Meses com Multiplas Folhas")
    table.add_column("Mes")
    table.add_column("Qtd. Folhas", justify="right")
    table.add_column("Num. Folhas")
    table.add_column("Descricoes")
    for row in rows:
        table.add_row(
            str(row["mes_ano"]),
            str(row["quantidade_folhas"]),
            ", ".join(str(item) for item in row["num_folhas"]),
            ", ".join(row["descricoes"]),
        )
    return table


def _falhas_table(title: str, rows: list[dict[str, Any]]) -> Table:
    table = Table(title=title)
    if not rows:
        return table
    columns = list(rows[0].keys())
    for column in columns:
        table.add_column(column)
    for row in rows:
        table.add_row(*(str(row.get(column, "")) for column in columns))
    return table
