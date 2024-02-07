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
import time
from datetime import timedelta


cache = diskcache.Cache('./cache')
lcm = DiskcacheLongCallbackManager(cache)

app = dash.Dash(__name__,
                external_stylesheets=[dbc.themes.SIMPLEX,
                                      'https://fonts.googleapis.com/css2?family=Libre+Baskerville&display=swap'],
                long_callback_manager=lcm)

server = app.server
# server.wsgi_app = WhiteNoise(server.wsgi_app, root='static/')

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
            start = time.time()
            save_pdf(url)
            end = time.time()
            print('save_pdf: ', timedelta(seconds=end - start))

            start = time.time()
            df = get_scanned_pdf()
            end = time.time()
            print('get_scanned_pdf: ', timedelta(seconds=end - start))

            start = time.time()
            df = clean_scanned(df)
            end = time.time()
            print('clean_scanned: ', timedelta(seconds=end - start))

            start = time.time()
            df = join_dfs(df)
            df = df.rename(columns={'meps': 'MEP', 'am_no': 'Amendment Number',
                                    'article': 'Article', 'justification': 'Justification'})
            end = time.time()
            print('join_dfs: ', timedelta(seconds=end - start))

            start = time.time()
            df_total = add_scraped_info(df=df)
            end = time.time()
            print('add_scraped_info: ', timedelta(seconds=end - start))

            # Add topics
            start = time.time()
            df_total, nmf, feature_names = add_topics(df_total)
            end = time.time()
            print('add_topics: ', timedelta(seconds=end - start))

            # ---------------------------------------------------------------------------------------------------------------
            # Data table
            start = time.time()
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
                    {"name": "Country", "id": "Country"},
                    {"name": "Topic", "id": "Topic"},
                    ]
            end = time.time()
            print('scraped_df.to_dict: ', timedelta(seconds=end - start))
            # ---------------------------------------------------------------------------------------------------------------
            # Network graph
            start = time.time()
            stylesheet = [{'selector': 'node',
                           'style': {
                               'label': 'data(label)',
                               'shape': 'circle',
                               'background-color': '#d9230f'
                           }},
                          {'selector': 'edge',
                           'style': {'width': 'data(weight)'}}]

            elements = get_network_elements_v2(df_total)
            end = time.time()
            print('get_network_elements_v2: ', timedelta(seconds=end - start))

            # ---------------------------------------------------------------------------------------------------------------
            # Topic chart
            wcs = []
            for topic_idx, topic in enumerate(nmf.components_):
                img_wc = plot_wordcloud(topic=topic, feature_names=feature_names, n_words=20,
                                        title=f'Topic {topic_idx}')
                wcs.append(dbc.Card(
                    [
                        dbc.CardBody(
                            [
                                html.H4(f"Topic {topic_idx + 1}", className="card-title"),
                                html.Img(src="data:image/png;base64," + img_wc)
                            ]
                        ),
                    ],
                    style={"width": "16rem",
                           "margin-left": "1%",
                           'margin-bottom': '1%', },
                ))

            # ---------------------------------------------------------------------------------------------------------------
            # Polar chart
            start = time.time()
            df_polar = df_total.groupby(['European Group',
                                         'Article']).size().reset_index(name='Number of Amendments').copy()
            if len(df_polar) >= 20:
                df_polar = df_polar[df_polar['Article'].isin(
                    df_polar.groupby('Article')['Number of Amendments'].sum().nlargest(20).index)]

            color_discrete_map = {"Group of the European People's Party (Christian Democrats)": '#003f86',
                                  'European Conservatives and Reformists Group': '#0285fd',
                                  'Renew Europe Group': '#fea607',
                                  'Group of the Greens/European Free Alliance': '#27c201',
                                  'Group of the Progressive Alliance of Socialists and Democrats in the European Parliament':
                                      '#d41011',
                                  'The Left group in the European Parliament - GUE/NGL': '#4c0203',
                                  'Non-attached Members': '#cbcbcb',
                                  'Identity and Democracy Group': '#879c8f'}

            fig_polar = px.bar_polar(df_polar, r="Number of Amendments", theta="Article", color="European Group",
                                     color_discrete_map=color_discrete_map, template='plotly_white',
                                     title='Top 20 most amended articles')
            fig_polar.update_layout(
                font_family="sans-serif")
            fig_polar.update_layout({
                'plot_bgcolor': '#fcfcfc',
                'paper_bgcolor': '#fcfcfc',
            })
            fig_polar.update_layout(showlegend=False)
            end = time.time()
            print('polar: ', timedelta(seconds=end - start))

            # ---------------------------------------------------------------------------------------------------------------
            # Barchart
            start = time.time()
            df_counts = df_total[['MEP']]
            df_counts = df_counts.value_counts().rename_axis('MEP').reset_index(name='Number of amendments')
            df_bar = df_total.merge(df_counts, how='right', on='MEP')
            df_bar = df_bar.drop_duplicates(subset=['MEP', 'Number of amendments', 'European Group'])
            end = time.time()
            print('add_scraped_info_no_diff: ', timedelta(seconds=end - start))

            start = time.time()

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
            end = time.time()
            print('fig_bar: ', timedelta(seconds=end - start))

            # ---------------------------------------------------------------------------------------------------------------
            # Cards
            #headers = {
            #    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.106 Safari/537.36'}
            start = time.time()
            cards = []
            df_total['id'] = df_total['MEP'].map(hash)
            for mep in df_total['MEP'].unique():

                # get picture link
                img_url = df_total[df_total['MEP'] == mep]['picture_link'].iloc[0]
                party = df_total[df_total['MEP'] == mep]['European Group'].iloc[0]
                country = df_total[df_total['MEP'] == mep]['Country'].iloc[0]
                id_mep = df_total[df_total['MEP'] == mep]['id'].iloc[0]

                if pd.isna(img_url) == False:
                    #response = requests.get(img_url, stream=True, headers=headers)
                    #response = requests.get(img_url, stream=True)

                    # save picture
                    #with open(f'assets\\{id_mep}.png', 'bw') as img_file:
                        #img_file.write(response.content)

                    card = dbc.Card(
                        [
                            dbc.CardImg(
                                #src=f'assets\\{id_mep}.png', alt='image',
                                src=img_url, alt='image',
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
            end = time.time()
            print('cards: ', timedelta(seconds=end - start))

            # ---------------------------------------------------------------------------------------------------------------
            # Dynamic layout
            start = time.time()
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
                        filter_action="native",
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
                    dbc.Col([dcc.Graph(id='sunburst', figure=fig_polar)], style={'width': '40%', 'height': '450px'}),
                    dbc.Col([dcc.Graph(id='barchart', figure=fig_bar)], style={'width': '60%', 'height': '450px'}),
                ]),
                html.H5("Who are the MEPs involved?", style={'margin-left': '4%',
                                                             'margin-top': '4%', }),
                dbc.Col(dbc.Row(children=cards,
                                style={'overflow-x': 'scroll', 'margin-left': '4%', 'margin-right': '4%',
                                       'height': '400px', },
                                id="cards-output",
                                )),
                html.H5("What is this document about?", style={'margin-left': '4%',
                                                        'margin-top': '4%'}),
                dbc.Col(
                    dbc.Row(children=wcs, style={'overflow-x': 'scroll', 'margin-left': '4%', 'margin-right': '4%',
                                                 'height': '400px'}, id="wordclouds")
                )
            ]
            end = time.time()
            print('dynami layout: ', timedelta(seconds=end - start))
            return dynamic_layout


if __name__ == '__main__':
    app.run_server()
