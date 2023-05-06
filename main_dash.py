import dash
import dash_bootstrap_components as dbc
import pandas as pd
import plotly.graph_objs as go
from dash import Input, Output, dcc, html, State, dash_table
from utils import *


app = dash.Dash(external_stylesheets=[dbc.themes.SIMPLEX,
                                      'https://fonts.googleapis.com/css2?family=Libre+Baskerville&display=swap',
                                      ])

app.css.config.serve_locally = True

# Layout ---------------------------------------------------------------------------------------------------------------

app.layout = dbc.Container(
    [
        html.H1("EP Amendments Analyser", style={'margin-left': '4%',
                                                 'margin-top': '4%'}),
        html.Hr(),
        html.P(["Start by inputting a link to an European Parliament pdf amendment document. "
               "You can find multiple examples ",
                html.A("here", href = "https://www.europarl.europa.eu/committees/en/documents/search?committeeMnemoCode=&textualSearchMode=TITLE&textualSearch=&documentTypeCode=AMCO&reporterPersId=&procedureYear=&procedureNum=&procedureCodeType=&peNumber=&sessionDocumentDocTypePrefix=&sessionDocumentNumber=&sessionDocumentYear=&documentDateFrom=&documentDateTo=&meetingDateFrom=&meetingDateTo=&performSearch=true&term=9&page=0"),
               "."], style={'margin-left': '4%'}),
        dbc.Row([
                dbc.Input(
                    id='url_input',
                    type="url",
                    placeholder="Input a pdf document url",
                    style={'width':'70%',
                           'margin-left': '5%',
                           'margin-right': '5%'}),
                dbc.Button('Go!', id='button', className="me-2", n_clicks=0, style={'width':'10%',
                       'margin-left': '5%'})],
            align="center"),

        dbc.Row([
            dash_table.DataTable(
                id='table',
                row_selectable="multi",
                sort_action="native",
                sort_mode="multi",
                export_format='xlsx',
                #export_headers='display',
                #filter_action="native",
                fixed_rows={'headers': True},
                style_table={'overflowX': 'auto',
                             'overflowY': 'auto',
                             'height': '300px',
                             'border': '1px solid black',
                             'borderRadius': '15px',
                             'overflow': 'hidden'
                             },
                style_cell={
                    'textOverflow': 'ellipsis',
                    'minWidth': '180px',
                    'width': '180px',
                    'maxWidth': '180px',
                    'whiteSpace': 'normal',
                    'font-family':'sans-serif',
                    'textAlign': 'left'},

    ),
        ], style={'width':'95%',
                  'margin': 'auto',
                  'margin-top':'3%'}),
    ],
    fluid=True,
)



# Callbacks ------------------------------------------------------------------------------------------------------------

@app.callback(
    Output('table', 'data'),
    Input('button', 'n_clicks'),
    State('url_input', 'value'),
)
def add_rows(n_clicks,url):
    if n_clicks > 0:
        save_pdf(url)
        df = get_scanned_pdf()
        df = clean_scanned(df)
        df = join_dfs(df)
        df = df.rename(columns={'meps': 'MEP', 'am_no': 'Amendment #',
                                'article': 'Article', 'justification': 'Justification'})
        dataframe = df.to_dict('records')
    return dataframe

if __name__ == '__main__':
    app.run_server()