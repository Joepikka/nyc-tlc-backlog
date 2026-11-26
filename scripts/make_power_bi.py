"""Write the editable Power BI report and semantic model."""

import hashlib
import json
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "report"
NAME = "NYC TLC"
SCHEMA = "https://developer.microsoft.com/json-schemas/fabric"
REPORT_SCHEMA = "item/report/definition"
MODEL = f"{NAME}.SemanticModel"
REPORT = f"{NAME}.Report"
NAVY = "#12293F"
TEAL = "#087E85"
SLATE = "#456178"


def write(relative, content):
    path = OUT / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def document(relative, schema, **properties):
    write(relative, json.dumps({"$schema": f"{SCHEMA}/{schema}/schema.json", **properties},
                              indent=2, ensure_ascii=False) + "\n")


def platform(folder, item_type):
    identity = str(uuid5(NAMESPACE_URL, f"nyc-tlc-q1-2025/{item_type}"))
    document(f"{folder}/.platform", "gitIntegration/platformProperties/2.0.0",
             metadata={"type": item_type, "displayName": NAME},
             config={"version": "2.0", "logicalId": identity})


def table(name, columns, partition, measures=(), metadata=""):
    lines = [f"table '{name}'", metadata]
    for measure, formula, fmt in measures:
        lines += [f"\tmeasure '{measure}' = {formula}", f"\t\tformatString: {fmt}", ""]
    for display, source, data_type, fmt, attributes in columns:
        lines += [f"\tcolumn '{display}'", f"\t\tdataType: {data_type}",
                  f"\t\tsourceColumn: {source}", "\t\tsummarizeBy: none"]
        if fmt:
            lines.append(f"\t\tformatString: {fmt}")
        if attributes:
            lines.append(f"\t\t{attributes}")
        lines.append("")
    lines.append(partition)
    write(f"{MODEL}/definition/tables/{name}.tmdl", "\n".join(lines) + "\n")


def import_csv(name, filename, columns):
    types = {"string": "type text", "int64": "Int64.Type", "dateTime": "type date"}
    column_types = ", ".join(f'{{"{source}", {types[data_type]}}}' for _, source, data_type, *_ in columns)
    return (
        f"\tpartition '{name}' = m\n"
        "\t\tmode: import\n"
        "\t\tsource =\n"
        "\t\t\tlet\n"
        f'\t\t\t    Source = Csv.Document(File.Contents(ExportFolder & "\\{filename}"), '
        f'[Delimiter = ",", Columns = {len(columns)}, Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),\n'
        "\t\t\t    Headers = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),\n"
        f'\t\t\t    Typed = Table.TransformColumnTypes(Headers, {{{column_types}}}, "en-US")\n'
        "\t\t\tin\n"
        "\t\t\t    Typed"
    )


def make_model():
    platform(MODEL, "SemanticModel")
    document(f"{MODEL}/definition.pbism", "item/semanticModel/definitionProperties/1.0.0",
             version="4.2", settings={"qnaEnabled": False})
    write(f"{MODEL}/definition/database.tmdl", "database\n\tcompatibilityLevel: 1600\n")
    write(f"{MODEL}/definition/model.tmdl", """model Model
\tculture: en-US
\tdefaultPowerBIDataSourceVersion: powerBI_V3
\tsourceQueryCulture: en-US

\tannotation PBI_QueryOrder = ["ExportFolder","Daily","March 31 Worklist","Problem","Borough"]
\tannotation __PBI_TimeIntelligenceEnabled = 0
""")
    folder = str(ROOT / "exports").replace('"', '""')
    write(f"{MODEL}/definition/expressions.tmdl",
          f'expression ExportFolder = "{folder}" meta [IsParameterQuery = true, Type = "Text", IsParameterQueryRequired = true]\n')
    daily_columns = [
        ("Day", "day", "dateTime", "MMM d, yyyy", "isHidden"),
        ("Problem", "problem", "string", None, "isHidden"),
        ("Borough", "borough", "string", None, "isHidden"),
        *((label, source, "int64", "#,0", "isHidden") for label, source in [
            ("Arrivals Raw", "arrivals"), ("Closures Raw", "closures"),
            ("Backlog Raw", "backlog"), ("Aged Raw", "aged30")]),
    ]
    last_day = "VAR LastDay = MAX('Dates'[Date]) RETURN "
    table("Daily", daily_columns, import_csv("Daily", "daily.csv", daily_columns), [
        ("Arrivals", "SUM(Daily[Arrivals Raw])", "#,0"),
        ("Recorded closures", "SUM(Daily[Closures Raw])", "#,0"),
        ("Net change", "[Arrivals] - [Recorded closures]", "+#,0;-#,0;0"),
        ("Closing backlog", last_day + "CALCULATE(SUM(Daily[Backlog Raw]), 'Dates'[Date] = LastDay)", "#,0"),
        ("Aged 30+ cases", last_day + "CALCULATE(SUM(Daily[Aged Raw]), 'Dates'[Date] = LastDay)", "#,0"),
        ("Aged 30+ share", "DIVIDE([Aged 30+ cases], [Closing backlog])", "0.0%"),
    ])
    worklist_columns = [
        ("Request key", "unique_key", "string", None, "isKey"),
        ("Problem", "problem", "string", None, None),
        ("Borough", "borough", "string", None, None),
        ("Created date", "created_day", "dateTime", "MMM d, yyyy", None),
        ("Age (days)", "age_days", "int64", "0", None),
    ]
    table("March 31 Worklist", worklist_columns, import_csv("March 31 Worklist", "open_march31.csv", worklist_columns))
    table("Dates", [("Date", "[Date]", "dateTime", "MMM d, yyyy", "isKey")],
          "\tpartition Dates = calculated\n\t\tmode: import\n"
          "\t\tsource = CALENDAR(DATE(2025,1,1), DATE(2025,3,31))",
          metadata="\tdataCategory: Time\n")

    relationships = ["relationship dates_daily\n\tfromColumn: Daily.Day\n\ttoColumn: Dates.Date"]
    for dimension, source in [("Problem", "problem"), ("Borough", "borough")]:
        table(dimension, [(dimension, source, "string", None, "isKey")],
              f'\tpartition {dimension} = m\n\t\tmode: import\n'
              f'\t\tsource = Table.Distinct(Table.SelectColumns(Daily, {{"{source}"}}))')
        for fact in ("Daily", "'March 31 Worklist'"):
            name = f"{dimension.lower()}_{'daily' if fact == 'Daily' else 'worklist'}"
            relationships.append(f"relationship {name}\n\tfromColumn: {fact}.{dimension}\n"
                                 f"\ttoColumn: {dimension}.{dimension}")
    write(f"{MODEL}/definition/relationships.tmdl", "\n\n".join(relationships) + "\n")


def projection(table, column, measure=False):
    return {"field": {"Measure" if measure else "Column": {
        "Expression": {"SourceRef": {"Entity": table}}, "Property": column,
    }}, "queryRef": f"{table}.{column}", "nativeQueryRef": column}


def literal(value):
    return {"expr": {"Literal": {"Value": value}}}


def color(value):
    return {"solid": {"color": literal(f"'{value}'")}}


def properties(**settings):
    return [{"properties": settings}]


def card_format():
    return {"labels": properties(color=color(NAVY), fontSize=literal("32D"), labelDisplayUnits=literal("0D")),
            "categoryLabels": properties(color=color(SLATE), fontSize=literal("12D"))}


def visual(page, label, kind, pos, order, *, wells=None, sort=(), objects=None, title=None, panel=True):
    x, y, width, height = pos
    identity = hashlib.sha1(f"{page}/{label}".encode()).hexdigest()[:20]
    details = {"visualType": kind, "drillFilterOtherVisuals": True}
    if wells:
        details["query"] = {"queryState": {role: {"projections": projections} for role, projections in wells.items()}}
        if sort:
            details["query"]["sortDefinition"] = {"sort": [
                {"field": field["field"], "direction": direction} for field, direction in sort]}
    if objects:
        details["objects"] = objects
    container = {"background": properties(show=literal(str(panel).lower()), color=color("#FFFFFF"),
                                          transparency=literal("0D"))}
    if panel:
        container["border"] = properties(show=literal("true"), color=color("#D7E2EB"), radius=literal("8D"))
    if title:
        container["title"] = properties(show=literal("true"), text=literal(f"'{title}'"),
                                         fontColor=color(NAVY), fontSize=literal("13D"), bold=literal("true"))
    details["visualContainerObjects"] = container
    document(f"{REPORT}/definition/pages/{page}/visuals/{identity}/visual.json",
             f"{REPORT_SCHEMA}/visualContainer/2.7.0", name=identity,
             position=dict(x=x, y=y, z=order, width=width, height=height, tabOrder=order),
             visual=details)


def textbox(page, label, pos, order, lines):
    paragraphs = [{"textRuns": [{"value": value, "textStyle": {
        "fontFamily": "'Segoe UI', Arial, sans-serif", "fontSize": f"{size}pt",
        "color": text_color, "fontWeight": "bold" if bold else "normal",
    }}]} for value, size, text_color, bold in lines]
    visual(page, label, "textbox", pos, order, objects={"general": properties(paragraphs=paragraphs)}, panel=False)


def slicer(page, title, pos, order, field, mode="Dropdown", selection=None):
    objects = {"data": properties(mode=literal(f"'{mode}'"))}
    if selection:
        column = field["field"]["Column"]
        entity = column["Expression"]["SourceRef"]["Entity"]
        selected_field = {"Column": {"Expression": {"SourceRef": {"Source": "s"}},
                                     "Property": column["Property"]}}
        objects["general"] = properties(filter={"filter": {
            "Version": 2,
            "From": [{"Name": "s", "Entity": entity, "Type": 0}],
            "Where": [{"Condition": {"In": {
                "Expressions": [selected_field],
                "Values": [[{"Literal": {"Value": f"'{selection}'"}}]],
            }}}],
        }})
    visual(page, title, "slicer", pos, order, wells={"Values": [dict(field, active=True)]},
           objects=objects)


def make_report():
    platform(REPORT, "Report")
    document(f"{NAME}.pbip", "pbip/pbipProperties/1.0.0", version="1.0",
             artifacts=[{"report": {"path": REPORT}}], settings={"enableAutoRecovery": True})
    document(f"{REPORT}/definition.pbir", "item/report/definitionProperties/2.0.0", version="4.0",
             datasetReference={"byPath": {"path": f"../{MODEL}"}})
    document(f"{REPORT}/definition/version.json", f"{REPORT_SCHEMA}/versionMetadata/1.0.0", version="2.0.0")
    document(f"{REPORT}/definition/report.json", f"{REPORT_SCHEMA}/report/1.0.0", layoutOptimization="None",
             themeCollection={"baseTheme": {"name": "CY24SU02", "reportVersionAtImport": "5.55",
                                            "type": "SharedResources"}})
    health, review = "queueHealth", "marchWorklist"
    document(f"{REPORT}/definition/pages/pages.json", f"{REPORT_SCHEMA}/pagesMetadata/1.0.0",
             pageOrder=[health, review], activePageName=health)
    for page, title in [(health, "Queue health"), (review, "Review list · March 31")]:
        document(f"{REPORT}/definition/pages/{page}/page.json", f"{REPORT_SCHEMA}/page/2.0.0",
                 name=page, displayName=title, displayOption="FitToPage", width=1320, height=820,
                 objects={"background": properties(color=color("#F3F6FA"), transparency=literal("0D"))})

    textbox(health, "header", (28, 10, 1264, 115), 0, [
        ("NYC TLC  /  Q1 2025", 14, TEAL, True),
        ("Service request backlog", 29, NAVY, True),
        ("January 1–March 31, 2025  ·  Requests created since January 2024", 11, SLATE, False),
    ])
    date_field = projection("Dates", "Date")
    problem = projection("Problem", "Problem")
    borough = projection("Borough", "Borough")
    slicer(health, "Date range", (28, 132, 406, 94), 1, date_field, "Between")
    slicer(health, "Problem", (457, 132, 406, 94), 2, problem)
    slicer(health, "Borough", (886, 132, 406, 94), 3, borough)

    for offset, measure in enumerate(("Closing backlog", "Net change", "Aged 30+ share")):
        visual(health, measure, "card", (28 + offset * 429, 242, 406, 106), 4 + offset,
               wells={"Values": [projection("Daily", measure, True)]}, objects=card_format())
    backlog = projection("Daily", "Closing backlog", True)
    net = projection("Daily", "Net change", True)
    visual(health, "trend", "lineChart", (28, 364, 607, 396), 7,
           wells={"Category": [dict(date_field, active=True)], "Y": [backlog]},
           sort=[(date_field, "Ascending")], title="Open requests at end of day",
           objects={"dataPoint": properties(defaultColor=color(TEAL))})
    visual(health, "net change by problem", "barChart", (655, 364, 637, 396), 8,
           wells={"Category": [dict(problem, active=True)], "Y": [net]},
           sort=[(net, "Descending")], title="Backlog change by problem",
           objects={"dataPoint": properties(defaultColor=color(TEAL)),
                    "labels": properties(show=literal("true"), labelDisplayUnits=literal("0D"))})
    textbox(health, "definitions", (28, 772, 1264, 36), 9, [
        ("Closing backlog and 30+ share use the last selected day. Net change equals arrivals minus recorded closures.",
         11, SLATE, False),
    ])
    textbox(review, "header", (28, 10, 1264, 115), 0, [
        ("NYC TLC  /  MARCH 31, 2025", 14, TEAL, True),
        ("Supervisor review list", 29, NAVY, True),
        ("Fixed end-of-day snapshot  ·  Requests created since January 2024", 11, SLATE, False),
    ])
    slicer(review, "Problem", (28, 132, 406, 94), 1, problem, selection="Taxi Complaint")
    slicer(review, "Borough", (457, 132, 406, 94), 2, borough)
    textbox(review, "review instructions", (886, 134, 406, 92), 3, [
        ("Review the oldest cases first", 15, NAVY, True),
        ("Change Problem to review another queue. Ties are sorted by request key.", 11, SLATE, False),
    ])
    fields = [projection("March 31 Worklist", column) for column in
              ("Request key", "Problem", "Borough", "Created date", "Age (days)")]
    visual(review, "open requests", "tableEx", (28, 242, 1264, 518), 4,
           wells={"Values": fields}, sort=[(fields[-1], "Descending"), (fields[0], "Ascending")],
           title="Requests open at the March 31 cutoff",
           objects={"columnHeaders": properties(fontColor=color("#FFFFFF"), backColor=color(NAVY),
                                                fontSize=literal("12D"), autoSizeColumnWidth=literal("true"),
                                                columnAdjustment=literal("'growToFit'")),
                    "values": properties(fontSize=literal("12D")),
                    "grid": properties(rowPadding=literal("7D")),
                    "total": properties(totals=literal("false"))})
    textbox(review, "age note", (28, 772, 1264, 36), 5, [
        ("Age counts calendar days since creation. Use the Excel worklist to track reviewer actions and follow-up dates.",
         11, SLATE, False),
    ])


if __name__ == "__main__":
    make_model()
    make_report()
