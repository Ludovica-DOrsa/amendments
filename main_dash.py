import dash
import dash_bootstrap_components as dbc
import pandas as pd
import plotly.graph_objs as go
from dash import Input, Output, dcc, html, State, dash_table
from utils import *
import plotly.express as px


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
                markdown_options={"html": True},
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
        dbc.Row([
            cyto.Cytoscape(
                id='network_graph',
                layout={'name': 'grid'},
                elements=[],
                stylesheet = [{'selector': 'node',
                                'style': {'shape': 'circle',
                                'label': 'data(label)',
                                'background-color': '#d9230f',
                                "font-family": "sans-serif",}},
                                {'selector': 'edge',
                                 'style': {'width': 'data(weight)'}}],

                style={'width': '100%', 'height': '900px'}
            ),

        ],
            style={'width': '95%',
                   'margin': 'auto',
                   'margin-top': '3%'}
        ),
        dbc.Row([
            dbc.Col([dcc.Graph(id='sunburst'),], style={'width': '40%', 'height': '450px'}),
            dbc.Col([dcc.Graph(id='barchart')], style={'width': '60%', 'height': '450px'}),
        ])
    ],
    fluid=True,
)



# Callbacks ------------------------------------------------------------------------------------------------------------

@app.callback(
    Output('table', 'data'),
    Output('table', 'columns'),
    Input('button', 'n_clicks'),
    State('url_input', 'value'),
)
def add_rows(n_clicks,url):
    if n_clicks > 0:
        save_pdf(url)
        df = get_scanned_pdf()
        df = clean_scanned(df)
        df = join_dfs(df)
        df = df.rename(columns={'meps': 'MEP', 'am_no': 'Amendment Number',
                                'article': 'Article', 'justification': 'Justification'})
        df_total = add_scraped_info(df=df)
        dataframe = df_total.to_dict('records')
        cols = [{"name": "MEP", "id": "MEP"},
                   {"name": "Amendment #", "id": "Amendment #"},
                   {"name": "Article", "id": "Article"},
                   {"name": "Justification", "id": "Justification"},
                   {"name": "Amendment", "id": "Amendment"},
                   {"name": "Text proposed by the Commission", "id": "Text proposed by the Commission"},
                   {"name": "Modified Text", "id": "Modified Text", "presentation": "markdown"},
                   {"name": "European Group", "id": "European Group"},
                   {"name": "Country", "id": "Country"}]
    return dataframe, cols


@app.callback(
    Output('network_graph', 'elements'),
    Input('button', 'n_clicks'),
    State('url_input', 'value'),
    #prevent_initial_call=True
)
def get_network_graph(n_clicks,url):
    if n_clicks > 0:
        save_pdf(url)
        df = get_scanned_pdf()
        df = clean_scanned(df)
        df = join_dfs(df)
        df = df.rename(columns={'meps': 'MEP', 'am_no': 'Amendment Number',
                                'article': 'Article', 'justification': 'Justification'})
        elements = get_network_elements(df)

    return elements


@app.callback(
    Output('sunburst', 'figure'),
    Input('button', 'n_clicks'),
    State('url_input', 'value'),
    #prevent_initial_call=True
)
def get_sunburst(n_clicks,url):
    if n_clicks > 0:
        save_pdf(url)
        df = get_scanned_pdf()
        df = clean_scanned(df)
        df = join_dfs(df)
        df = df.rename(columns={'meps': 'MEP', 'am_no': 'Amendment Number',
                                'article': 'Article', 'justification': 'Justification'})
        df = df[['Amendment Number', 'Article']]
        df['value'] = 1
        fig = px.sunburst(df, path=['Article', 'Amendment Number'], values='value',
                          color_discrete_sequence=px.colors.sequential.Reds)
        fig.update_layout(
            font_family="sans-serif")
        fig.update_layout({
            'plot_bgcolor': '#fcfcfc',
            'paper_bgcolor': '#fcfcfc',
        })
    return(fig)

@app.callback(
    Output('barchart', 'figure'),
    Input('button', 'n_clicks'),
    State('url_input', 'value'),
    #prevent_initial_call=True
)
def get_barchart(n_clicks,url):
    if n_clicks > 0:
        save_pdf(url)
        df = get_scanned_pdf()
        df = clean_scanned(df)
        df = join_dfs(df)
        df = df.rename(columns={'meps': 'MEP', 'am_no': 'Amendment Number',
                                'article': 'Article', 'justification': 'Justification'})
        df = df[['MEP']]
        df = df.value_counts().rename_axis('MEP').reset_index(name='Number of amendments')

        df_total = add_scraped_info_no_diff(df=df)

        color_discrete_map = {"Group of the European People's Party (Christian Democrats)": '#003f86',
                              'European Conservatives and Reformists Group': '#0285fd',
                              'Renew Europe Group': '#fea607',
                              'Group of the Greens/European Free Alliance':'#27c201',
                              'Group of the Progressive Alliance of Socialists and Democrats in the European Parliament':
                                  '#d41011',
                              'The Left group in the European Parliament - GUE/NGL':'#4c0203',
                              'Non-attached Members':'#cbcbcb',
                              'Identity and Democracy Group':'#879c8f'}

        fig = px.bar(df_total, x='Number of amendments', y='MEP', template='plotly_white',
                     labels={
                         "MEP": ""
                     },
                     color='European Group',
                     color_discrete_map=color_discrete_map)
        fig.update_layout(
            font_family="sans-serif")
       # fig.update_layout(yaxis=dict(autorange="reversed"))
        fig.update_layout(showlegend=False)
        fig.update_layout(yaxis={'categoryorder': 'total ascending'})
        fig.update_layout({
            'plot_bgcolor': '#fcfcfc',
            'paper_bgcolor': '#fcfcfc',
        })
    return(fig)

if __name__ == '__main__':
    app.run_server()