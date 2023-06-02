import dash
import dash_bootstrap_components as dbc
import pandas as pd
import plotly.graph_objs as go
from dash import Input, Output, dcc, html, State, dash_table
from utils import *
import plotly.express as px
import gunicorn
from dash.exceptions import PreventUpdate
from dash.long_callback import DiskcacheLongCallbackManager
import diskcache
#from whitenoise import WhiteNoise

cache = diskcache.Cache('./cache')
lcm = DiskcacheLongCallbackManager(cache)

app = dash.Dash(__name__,
                external_stylesheets=[dbc.themes.SIMPLEX,
                                      'https://fonts.googleapis.com/css2?family=Libre+Baskerville&display=swap'],
                long_callback_manager=lcm)

server = app.server
#server.wsgi_app = WhiteNoise(server.wsgi_app, root='static/')

app.css.config.serve_locally = True

# Layout ---------------------------------------------------------------------------------------------------------------

app.layout = dbc.Container(
    [
        html.H1("EP Amendments Analyser", style={'margin-left': '4%',
                                                 'margin-top': '4%'}),
        html.Hr(),
        html.P(["Start by inputting a link to an European Parliament pdf amendment document. "
                "You can find multiple examples ",
                html.A("here",
                       href="https://www.europarl.europa.eu/committees/en/documents/search?committeeMnemoCode=&textualSearchMode=TITLE&textualSearch=&documentTypeCode=AMCO&reporterPersId=&procedureYear=&procedureNum=&procedureCodeType=&peNumber=&sessionDocumentDocTypePrefix=&sessionDocumentNumber=&sessionDocumentYear=&documentDateFrom=&documentDateTo=&meetingDateFrom=&meetingDateTo=&performSearch=true&term=9&page=0"),
                "."], style={'margin-left': '4%'}),
        dbc.Row([
            dbc.Input(
                id='url_input',
                type="url",
                placeholder="Input a pdf document url",
                style={'width': '70%',
                       'margin-left': '5%',
                       'margin-right': '5%'}),
            dbc.Button('Go!', id='button', className="me-2", n_clicks=0, style={'width': '10%',
                                                                                'margin-left': '5%'})], align="center"),


        html.Div(id='output')
    ],
    fluid=True,
)


# Callbacks ------------------------------------------------------------------------------------------------------------

@app.long_callback(
    Output('output', 'children'),
    Input('button', 'n_clicks'),
    State('url_input', 'value'),
    prevent_initial_call=True
)
def return_divs(n_clicks, url):

    if n_clicks > 0:

            save_pdf(url)
            df = get_scanned_pdf()
            df = clean_scanned(df)
            df = join_dfs(df)
            df = df.rename(columns={'meps': 'MEP', 'am_no': 'Amendment Number',
                                    'article': 'Article', 'justification': 'Justification'})
            df_total = add_scraped_info(df=df)

            # ---------------------------------------------------------------------------------------------------------------
            # Data table
            scraped_df = df_total.copy()
            scraped_df = scraped_df.drop(['picture_link'], axis=1)
            dataframe = scraped_df.to_dict('records')
            cols = [{"name": "MEP", "id": "MEP"},
                    {"name": "Amendment #", "id": "Amendment #"},
                    {"name": "Article", "id": "Article"},
                    {"name": "Justification", "id": "Justification"},
                    {"name": "Amendment", "id": "Amendment"},
                    {"name": "Text proposed by the Commission", "id": "Text proposed by the Commission"},
                    {"name": "Modified Text", "id": "Modified Text", "presentation": "markdown"},
                    {"name": "European Group", "id": "European Group"},
                    {"name": "Country", "id": "Country"}]
            # ---------------------------------------------------------------------------------------------------------------
            # Network graph

            stylesheet = [{'selector': 'node',
                           'style': {
                               'label': 'data(label)',
                               'shape': 'circle',
                               'background-color': '#d9230f'
                           }},
                          {'selector': 'edge',
                           'style': {'width': 'data(weight)'}}]

            elements = get_network_elements_v2(df_total)

            # ---------------------------------------------------------------------------------------------------------------
            # Sunburst

            df_sun = df_total[['Amendment Number', 'Article']]
            df_sun['value'] = 1
            df_sun = df_sun.fillna('')
            fig_sun = px.sunburst(df_sun, path=['Article', 'Amendment Number'], values='value',
                                  color_discrete_sequence=px.colors.sequential.Reds,
                                  title='Which were the most amended articles?')
            fig_sun.update_layout(
                font_family="sans-serif")
            fig_sun.update_layout({
                'plot_bgcolor': '#fcfcfc',
                'paper_bgcolor': '#fcfcfc',
            })

            # ---------------------------------------------------------------------------------------------------------------
            # Barchart

            df_bar = df_total[['MEP']]
            df_bar = df_bar.value_counts().rename_axis('MEP').reset_index(name='Number of amendments')
            df_bar = add_scraped_info_no_diff(df=df_bar)

            color_discrete_map = {"Group of the European People's Party (Christian Democrats)": '#003f86',
                                  'European Conservatives and Reformists Group': '#0285fd',
                                  'Renew Europe Group': '#fea607',
                                  'Group of the Greens/European Free Alliance': '#27c201',
                                  'Group of the Progressive Alliance of Socialists and Democrats in the European Parliament':
                                      '#d41011',
                                  'The Left group in the European Parliament - GUE/NGL': '#4c0203',
                                  'Non-attached Members': '#cbcbcb',
                                  'Identity and Democracy Group': '#879c8f'}

            fig_bar = px.bar(df_bar, x='Number of amendments', y='MEP', template='plotly_white',
                             title='Who signed the most amendments?',
                             labels={
                                 "MEP": ""},
                             color='European Group',
                             color_discrete_map=color_discrete_map)
            fig_bar.update_layout(font_family="sans-serif")
            fig_bar.update_layout(showlegend=False)
            fig_bar.update_layout(yaxis={'categoryorder': 'total ascending'})
            fig_bar.update_layout({
                'plot_bgcolor': '#fcfcfc',
                'paper_bgcolor': '#fcfcfc',
            })

            # ---------------------------------------------------------------------------------------------------------------
            # Cards
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.106 Safari/537.36'}
            cards = []
            df_total['id'] = df_total['MEP'].map(hash)
            for mep in df_total['MEP'].unique():

                # get picture link
                img_url = df_total[df_total['MEP'] == mep]['picture_link'].iloc[0]
                party = df_total[df_total['MEP'] == mep]['European Group'].iloc[0]
                country = df_total[df_total['MEP'] == mep]['Country'].iloc[0]
                id_mep = df_total[df_total['MEP'] == mep]['id'].iloc[0]

                if pd.isna(img_url) == False:
                    response = requests.get(img_url, stream=True, headers=headers)

                    # save picture
                    with open(f'assets\\{id_mep}.png', 'bw') as img_file:
                        img_file.write(response.content)

                    card = dbc.Card(
                        [
                            dbc.CardImg(
                                # src=path_img,
                                src=f'assets\\{id_mep}.png', alt='image',
                                #src=f'assets\\dice.png', alt='image',
                                top=True),
                            dbc.CardBody(
                                [
                                    html.H4(f"{mep}", className="card-title"),
                                    html.P(
                                        f"Country: {country}",
                                        className="card-text",
                                    ),
                                    html.Br(),
                                    html.P(
                                        f"European Group: {party}",
                                        className="card-text",
                                    )
                                ]
                            ),
                        ],
                        style={"width": "16rem",
                               "margin-left": "1%",
                               'margin-bottom': '1%', },
                    )
                    cards.append(card)

                else:
                    card = dbc.Card(
                        [
                            dbc.CardBody(
                                [
                                    html.H4(f"{mep}", className="card-title"),
                                    html.P(
                                        f"Country: {country}",
                                        className="card-text",
                                    ),
                                    # html.Br(style={'display': 'block', 'margin-bottom': '0em'}),
                                    html.P(
                                        f"European Group: {party}",
                                        className="card-text",
                                    ),
                                ]
                            ),
                        ],
                        style={"width": "16rem",
                               "margin-left": "1%",
                               'margin-bottom': '1%', },
                    )
                    cards.append(card)

            # ---------------------------------------------------------------------------------------------------------------
            # Dynamic layout

            dynamic_layout = [
                dbc.Row([
                    dash_table.DataTable(
                        id='table',
                        data=dataframe,
                        columns=cols,
                        row_selectable="multi",
                        sort_action="native",
                        sort_mode="multi",
                        export_format='xlsx',
                        # export_headers='display',
                        # filter_action="native",
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
                            'font-family': 'sans-serif',
                            'textAlign': 'left'},

                    ),
                ], style={'width': '95%',
                          'margin': 'auto',
                          'margin-top': '3%'}),
                html.H5("Who worked with whom?", style={'margin-left': '4%',
                                                        'margin-top': '4%'}),
                dbc.Row([
                    cyto.Cytoscape(
                        id='network_graph',
                        layout={'name': 'grid'},
                        elements=elements,
                        stylesheet=stylesheet,
                        style={'width': '100%', 'height': '450px'}
                    ),

                ],
                    style={'width': '95%',
                           'margin': 'auto',
                           'margin-top': '3%'}
                ),
                dbc.Row([
                    dbc.Col([dcc.Graph(id='sunburst', figure=fig_sun)], style={'width': '40%', 'height': '450px'}),
                    dbc.Col([dcc.Graph(id='barchart', figure=fig_bar)], style={'width': '60%', 'height': '450px'}),
                ]),
                html.H5("Who are the MEPs involved?", style={'margin-left': '4%',
                                                             'margin-top': '4%', }),
                dbc.Col(dbc.Row(children=cards,
                                style={'overflow-x': 'scroll', 'margin-left': '4%', 'margin-right': '4%',
                                       'height': '400px', },
                                id="cards-output",
                                )),
            ]

            return dynamic_layout


if __name__ == '__main__':
    app.run_server()
