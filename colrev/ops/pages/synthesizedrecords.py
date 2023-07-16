#! /usr/bin/env python3
"""dashboard table and graphs for synthesized records"""
from __future__ import annotations

import dash
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dash import callback
from dash import dash_table
from dash import dcc
from dash import html
from dash import Input
from dash import Output

import colrev.record
import colrev.review_manager

dash.register_page(__name__)

review_manager = colrev.review_manager.ReviewManager()
status_operation = review_manager.get_status_operation()
records = review_manager.dataset.load_records_dict()
data = pd.DataFrame.from_records(
    [
        r
        for r in records.values()
        if r["colrev_status"] == colrev.record.RecordState.rev_synthesized
    ]
)

if data.empty:
    data = pd.DataFrame(columns=["author", "title", "year", "journal"])
else:
    data = data[["author", "title", "year", "journal"]]


def empty_figure() -> object:
    """creates an empty figure in case of invalid search"""
    figure = go.Figure(go.Scatter(x=[], y=[]))
    figure.update_layout(template=None)
    figure.update_xaxes(showgrid=False, showticklabels=False, zeroline=False)
    figure.update_yaxes(showgrid=False, showticklabels=False, zeroline=False)

    return figure


def plot_time(data_input: pd.DataFrame) -> object:
    """creates graph about papers published over time"""

    # check for data_input
    if data_input.empty:
        return empty_figure()

    # group data_input for the graph
    data2 = data_input.groupby(["year"])["year"].count().reset_index(name="count")

    # make and style the graph
    fig = px.bar(
        data2,
        x="year",
        y="count",
        template="simple_white",
        title="Profile of papers published over time",
        color="year",
    )
    fig.update_traces(marker_color="#fcb61a")

    fig.update_layout(
        title={
            "text": "<b>Profile of papers published over time</b>",
            "font": {"family": "Lato, sans-serif", "size": 30},
            "automargin": True,
            "x": 0.5,
        }
    )

    # style x axis
    fig.update_xaxes(
        title_text="Year",
        type="category",
        title_font={"family": "Lato, sans-serif", "size": 20},
        tickfont={"family": "Lato, sans-serif", "size": 20},
    )

    # style y axis
    fig.update_yaxes(
        title_text="Count",
        title_font={"family": "Lato, sans-serif", "size": 20},
        tickfont={"family": "Lato, sans-serif", "size": 20},
    )
    return fig


def plot_journals(data_input: pd.DataFrame) -> px.bar:
    """creates graph about papers published per journal"""

    # check for data_input
    if data_input.empty:
        return empty_figure()

    # group data for the graph
    data2 = data_input.groupby(["journal"])["journal"].count().reset_index(name="count")
    data2 = data2[data2["count"] != 0].sort_values(by="count", ascending=True)

    # make and style the graph
    fig = px.bar(
        data2,
        x="count",
        y="journal",
        template="simple_white",
        title="Papers Published per Journal",
        orientation="h",
    )
    fig.update_traces(marker_color="#fcb61a")

    fig.update_layout(
        title={
            "text": "<b>Papers Published per Journal</b>",
            "font": {"family": "Lato, sans-serif", "size": 30},
            "automargin": True,
            "x": 0.5,
        }
    )

    # style x axis
    fig.update_xaxes(
        title_text="Count",
        title_font={"family": "Lato, sans-serif", "size": 20},
        tickfont={"family": "Lato, sans-serif", "size": 15},
    )

    # style y axis
    fig.update_yaxes(
        title_text="Journal",
        type="category",
        title_font={"family": "Lato, sans-serif", "size": 20},
        tickfont={"family": "Lato, sans-serif", "size": 15},
    )

    return fig


# html layout for the synthesised records subpage
layout = html.Div(
    children=[
        html.Div(
            children=[
                html.Div(
                    # sorting dropdown
                    className="options",
                    children=[
                        dcc.Dropdown(
                            id="sortby",
                            options=["title", "year", "author (alphabetically)"],
                            placeholder="Sort by...",
                        )
                    ],
                ),
                html.Div(
                    # search bar
                    className="options",
                    children=[
                        dcc.Input(
                            type="text",
                            id="search",
                            value="",
                            placeholder="  Search for...",
                        )
                    ],
                ),
            ],
            className="menu",
        ),
        html.Div(
            children=[
                html.Div(
                    [
                        html.Label(
                            "Currently Synthesized Records",
                            style={
                                "font-family": "Lato, sans-serif",
                                "font-weight": "bold",
                                "fontSize": 30,
                            },
                        ),
                        # table with synthesized records
                        dash_table.DataTable(
                            data=data.to_dict("records"),
                            id="table",
                            style_cell={
                                "font-family": "Lato, sans-serif",
                                "font-size": "20px",
                                "text-align": "left",
                            },
                            style_cell_conditional=[
                                {
                                    "if": {"column_id": "year"},
                                    "width": "7%",
                                    "text-align": "center",
                                },
                                {"if": {"column_id": "title"}, "width": "53%"},
                            ],
                            style_header={
                                "font-weight": "bold",
                                "backgroundColor": "#006400",
                                "color": "white",
                            },
                            style_data={
                                "whiteSpace": "normal",
                                "height": "auto",
                                "border": "1px solid green",
                            },
                            style_as_list_view=True,
                        ),
                    ]
                ),
                # Div für Ausgabe wenn keine Ergebnisse bei Suche
                html.Div(id="table_empty", children=[]),
                # graph 1
                html.Div(
                    [dcc.Graph(figure=plot_time(data), id="time")],
                ),
                # graph 2
                html.Div(
                    [dcc.Graph(figure=plot_journals(data), id="magazines")],
                ),
            ],
            className="wrapper",
        ),
        # button to burn down chart
        html.Div(
            className="navigation-button",
            children=[
                html.A(
                    html.Button("back to Burn-Down Chart"),
                    href="http://127.0.0.1:8050/",
                )
            ],
        ),
    ]
)


@callback(
    Output("table", "data"),
    Output("table_empty", "children"),
    Output("time", "figure"),
    Output("magazines", "figure"),
    Input("search", "value"),
    Input("sortby", "value"),
)
def update_table(searchvalue, sortvalue) -> tuple[dict, str, px.bar, px.bar]:  # type: ignore
    """callback function updating table and graphs based on search and sort"""
    sorted_data = data.copy(deep=True)

    output = ""

    # sort data
    if sortvalue == "year":
        sorted_data = sorted_data.sort_values(by=["year"])  # sort by year
    elif sortvalue == "title":
        sorted_data = sorted_data.sort_values(by=["title"])  # sort by title
    elif sortvalue == "author":
        sorted_data = sorted_data.sort_values(by=["author"])  # sort by author

    data2 = sorted_data.copy(deep=True).to_dict("records")

    # search for data
    for row in sorted_data.to_dict("records"):
        found = False
        for key in row:
            if searchvalue.lower().strip() in str(row[key]).lower():
                found = True

        if found is False:
            data2.remove(row)

    # check if search results are empty
    if not data2:
        output = "No records included in the sample."

    return (
        data2,
        output,
        plot_time(pd.DataFrame.from_dict(data2)),
        plot_journals(pd.DataFrame.from_dict(data2)),
    )
