from __future__ import annotations
import pandas as pd
import requests
import fitz
import urllib.request
import re
from unidecode import unidecode
import numpy as np
import dash_cytoscape as cyto
from bs4 import BeautifulSoup
import difflib

url = 'https://www.europarl.europa.eu/doceo/document/ITRE-AM-746920_EN.pdf'

def save_pdf(url: str, name: str|None = None):
    """
    Retrieves pdf from url and saves it in pdf folden
    :param url: a url like https://www.europarl.europa.eu/doceo/document/ITRE-AM-746920_EN.pdf
    :param name: name of the saved pdf
    """
    if name:
        urllib.request.urlretrieve(url, f"pdfs/{name}.pdf")
    else:
        urllib.request.urlretrieve(url, "pdfs/download.pdf")


def get_scanned_pdf(path: str = "pdfs/download.pdf") -> pd.DataFrame:
    """
    Obtain a pandas df containing bounding boxes of blocks of text, the original text and additional information
    from a pdf file
    :param path: path of the file
    :return span_df: a pandas dataframe
    """
    doc = fitz.open(path) # Open pdf
    block_dict = {}
    page_num = 1
    for page in doc: # Iterate all pages in the document
        file_dict = page.get_text('dict') # Get the page dictionary
        block = file_dict['blocks'] # Get the block information
        block_dict[page_num] = block # Store in block dictionary
        page_num += 1 # Increase the page value by 1

    rows = []
    for page_num, blocks in block_dict.items(): # Iterate over blocks and pages
        for block in blocks:
            if block['type'] == 0:
                for line in block['lines']:
                    for span in line['spans']:
                        xmin, ymin, xmax, ymax = list(span['bbox']) # Get bounding box measurements
                        font_size = span['size']
                        #text = unidecode(span['text'])
                        #----------------------------
                        text = span['text']
                        span_font = span['font']
                        is_upper = False
                        is_bold = False
                        if "bold" in span_font.lower():
                            is_bold = True
                        if re.sub("[\(\[].*?[\)\]]", "", text).isupper():
                            is_upper = True
                        if text.replace(" ","") !=  "":
                            rows.append((xmin, ymin, xmax, ymax, text, is_upper, is_bold, span_font, font_size))
                            span_df = pd.DataFrame(rows, columns=['xmin','ymin','xmax','ymax', 'text', 'is_upper','is_bold','span_font', 'font_size'])
    return span_df


def clean_scanned(df: pd.DataFrame) -> pd.DataFrame:
    """
    Cleans the pandas df containing bounding boxes of blocks of text
    :param df:
    :return df:
    """

    # Remove text at the bottom of the page
    df = df[df['ymin'] <= 750]
    df = df[df['text'] != 'Or. en']
    # Create amendment number
    df['am_no'] = np.where(df.text.str.contains('Amendment [0-9]+', regex=True, na=False) == True, df['text'], np.NaN)

    #Only keep digits
    df['am_no'] = df['am_no'].str.replace(r'\D', '', regex=True)
    df['am_no'] = df['am_no'].str.replace(' ', '', regex=False)
    # The row below the amendment number contains MEP names
    df['meps'] = np.where(df['am_no'].shift(1).isna() == False, df['text'], np.NaN)

    # Occasionally the rows below also contain MEP names.
    # If the row above contains MEP names and the current does not contain "Proposal for a regulation/directive/decision/resolution",
    # it also contains MEP names
    df['meps'] = np.where((df['meps'].shift(1).isna() == False) &  # Previous row contains meps
                          ((df['text'].str.contains(r'((\bProposal\b)|(\bMotion\b)) for a ((\bregulation\b)|(\bdirective\b)|(\bdecision\b)|(\bresolution\b))',
                                                   regex=True, na=False) == False)),
                          # does not contain "Proposal for a regulation"
                          df['text'], df['meps'])

    df = df[df['meps']!=' ']

    # Forward fill amendment number
    df['am_no'] = df['am_no'].ffill()

    # Get max x of text proposed by the commission
    df['xmax_comm'] = np.where((df['text'] == 'Text proposed by the Commission')|
                               (df['text'] == 'Motion for a resolution')|
                               (df['text'] == 'Present text'), df['xmax'], np.NaN)
    df['xmax_comm'] = df.groupby('am_no')['xmax_comm'].ffill()
    # all text with xmin < xmax_comm is text proposed by the commission
    df['type'] = np.where(df['xmin'] < df['xmax_comm'], 'Text proposed by the Commission', np.NaN)
    # all text with xmin > xmax_comm is amendment text
    df['type'] = np.where(df['xmin'] > df['xmax_comm'], 'Amendment', df['type'])

    # Get article (the row below "Proposal for a regulation/directive/decision/resolution")
    #((\bregulation\b)|(\bdirective\b)|(\bdecision\b)|(\bresolution\b))
    df['article'] = np.where((df['text'].shift() == 'Proposal for a regulation')|
                             (df['text'].shift() == 'Proposal for a directive')|
                             (df['text'].shift() == 'Proposal for a decision')|
                             (df['text'].shift() == 'Proposal for a resolution')|
                             (df['text'].shift() == 'Motion for a resolution')
                             , df['text'], np.NaN)

    # Get justification - text below "Justification"
    df['justification'] = np.where(df['text'].shift() == 'Justification', df['text'], np.NaN)
    # If the text is below a justification and does not contain "Amendment" it is also part of the justification
    df['justification'] = np.where((df['justification'].shift().isna() == False) &
                                   (df['text'].str.contains('Amendment', regex=False, na=False) == False),
                                   df['text'], df['justification'])
    # If the text is a justification it is neither an amendment or the text proposed by the commission
    df['type'] = np.where(df['justification'].isna() == False, np.NaN, df['type'])

    return df


def find_differences(df: pd.DataFrame)-> pd.DataFrame:
    """
    Create a new column in df which describes the differences between the text proposed by the commission and the
    amendment text
    :param df: pandas dataframe obtained through clean_df
    :return:
    """
    for index, row in df.iterrows():
        b = row['Amendment']
        a = row['Text proposed by the Commission']
        new_text = ""
        if pd.isnull(a) == False:
            if pd.isnull(b) == False:
                m = difflib.SequenceMatcher(a=a, b=b)

                for tag, i1, i2, j1, j2 in m.get_opcodes():
                    # good = #d9230f
                    # bad = #139418
                    if tag == 'replace':
                        #x = f'<del>{a[i1:i2]}</del>'
                        x = f"<span style ='color: #d9230f'>{a[i1:i2]}</span>"
                        new_text = new_text + x
                        #y = f'<ins>{b[j1:j2]}</ins>'
                        y = f"<span style ='color: #139418'>{b[j1:j2]}</span>"
                        new_text = new_text + y
                    if tag == 'delete':
                        #x = f'<del>{a[i1:i2]}</del>'
                        x = f"<span style ='color: #d9230f'>{a[i1:i2]}</span>"
                        new_text = new_text + x
                    if tag == 'insert':
                        #x = f'<ins>{b[j1:j2]}</ins>'
                        x = f"<span style ='color: #139418'>{b[j1:j2]}</span>"
                        new_text = new_text + x
                    if tag == 'equal':
                        #x = f'{a[i1:i2]}'
                        x = f"<span style ='color: black'>{a[i1:i2]}</span>"
                        new_text = new_text + x
                df.loc[index, 'Modified Text'] = new_text
    return df


def get_mep_amendment(df: pd.DataFrame) -> pd.DataFrame:
    """
    Get MEP-Amendment correspondence
    :param df: df cleaned through clean_scanned
    :return df: df containing mep name and amendment number
    """
    # Get MEP-Amendment correspondence
    subdf = df[['meps', 'am_no']].copy()
    subdf = subdf.dropna()
    subdf['meps'] = subdf['meps'].str.replace('on behalf of the ', '', regex=False)
    subdf = subdf.assign(meps=df['meps'].str.split(', ')).explode('meps')
    return subdf


def get_article_amendment(df: pd.DataFrame) -> pd.DataFrame:
    """
    Get Article-Amendment correspondence
    :param df: df cleaned through clean_scanned
    :return df: df containing article and amendment number
    """
    # Get MEP-Amendment correspondence
    subdf = df[['article', 'am_no']].copy()
    subdf = subdf.dropna()
    return subdf


def get_justification_amendment(df: pd.DataFrame) -> pd.DataFrame:
    """
    Get Justification-Amendment correspondence
    :param df: df cleaned through clean_scanned
    :return df: df containing justification and amendment number
    """
    # Get MEP-Amendment correspondence
    subdf = df[['justification', 'am_no']].copy()
    subdf = subdf.dropna()
    subdf = subdf.groupby('am_no', as_index=False).agg({'justification' : ' '.join})
    return subdf


def get_text_by_type(df: pd.DataFrame) -> pd.DataFrame:
    """
    Divides text proposed by the commission from amendment
    :param df: df cleaned through clean_scanned
    :return df: df containing justification and amendment number
    """
    # Get MEP-Amendment correspondence
    subdf = df[['text', 'am_no', 'type']].copy()
    subdf = subdf.dropna()
    subdf = subdf[subdf['type'].isna() == False]
    subdf = subdf.groupby(['am_no', 'type'], as_index=False).agg({'text': ' '.join})
    subdf = subdf.pivot(index='am_no', columns='type', values='text')
    return subdf


def join_dfs(df: pd.DataFrame) -> pd.DataFrame:
    """
    Joins amendments with articles, meps, justification and text
    :param df: df cleaned through clean_scanned
    :return:
    """
    df_mep = get_mep_amendment(df)
    df_art = get_article_amendment(df)
    df_just = get_justification_amendment(df)
    df_text = get_text_by_type(df)

    df_total = df_mep.merge(df_art, on='am_no', how='outer')
    df_total = df_total.merge(df_just, on='am_no', how='outer')
    df_total = df_total.merge(df_text, on='am_no', how='outer')

    df_total = df_total.drop(['nan'], axis = 1)
    df_total = df_total[df_total['meps']!=""]

    df_total['Amendment'] = df_total['Amendment'].str.removesuffix('Justification')
    df_total['Amendment'] = df_total['Amendment'].str.removeprefix('Amendment')
    df_total['Text proposed by the Commission'] = df_total['Text proposed by the Commission'].str.removeprefix('Text proposed by the Commission')

    return df_total


def get_network_elements(df: pd.DataFrame)->list:
    """
    Transforms the df obtained by join_dfs into the elements of a network graph
    :param df: a pandas dataframe obtained by join_df2
    :return elements: a list containing the elements of a network graph
    """

    # Create a df containing the combinations of MEPs
    edges_df = pd.DataFrame()
    for amendment in df['Amendment Number'].unique():
        filter_df = df[df['Amendment Number'] == amendment].copy()
        for mep in filter_df['MEP'].unique():
            meplist = filter_df[filter_df['MEP'] != mep][['MEP']]
            meplist = meplist.rename(columns={'MEP': 'node2'})
            meplist['node1'] = mep
            #edges_df = edges_df.append(meplist, ignore_index=True)
            edges_df = pd.concat([edges_df, meplist])

    # Obtain count of combinations
    edges_df = edges_df.groupby(['node1', 'node2']).size().reset_index().rename(columns={0: 'count'})
    # Get a dictionary of ids for every mep
    id_dict = dict(enumerate(edges_df.node1.unique()))
    id_dict = {y: x for x, y in id_dict.items()}

    # Obtain nodes
    elements = []
    for mep in edges_df['node1'].unique():
        mep_id = id_dict[mep]
        # {'data': {'id': 'two', 'label': 'Node 2'}}
        d = {'data': {'id': mep_id, 'label': mep}, 'position': {'x': 75, 'y': 75}}
        elements.append(d)

    # Obtain edges
    for index, row in edges_df.iterrows():
        node1_id = id_dict[row['node1']]
        node2_id = id_dict[row['node2']]
        weight = row['count']
        # {'data': {'source': 'one', 'target': 'two'}}
        d = {'data': {'source': node1_id, 'target': node2_id, 'weight': weight}}
        elements.append(d)

    return elements


def scrape_info(df: pd.DataFrame,
                url: str = 'https://www.europarl.europa.eu/meps/en/directory/all/all') -> pd.DataFrame:
    """
    Scrapes information about mep nationality, picture and party from url
    :param df: df obtained by clean_df
    :param url: mep directory url
    :return:
    """
    webpage = requests.get(url)
    html = webpage.text
    soup = BeautifulSoup(html)

    total_df = pd.DataFrame()  # I create a df to save results

    for mep in df['MEP'].unique():  # For every mep in df I obtain her/his unique webpage on the ep website

        dicti = {"MEP": mep}  # i create a dictionary to save results

        #for img in soup.find_all("img", {"alt": re.compile(f"^{mep}$", re.I)}):
        img = soup.find_all("img", {"alt": re.compile(f"{mep}", re.I)})
        if len(img)>0:
            img = soup.find_all("img", {"alt": re.compile(f"{mep}", re.I)})[0]

            # I obtain the MEP's picture link, european party name and country from the mep's unique webpage

            x = img.parent.parent.parent.parent
            if x:
                href = x['href']
                webpage2 = requests.get(href)
                html2 = webpage2.text
                soup2 = BeautifulSoup(html2)

                for span in soup2.find_all("span", {"class": 'erpl_newshub-photomep'}):  # I obtain the png link
                    img = span.find("img")
                    if img:
                        picture_link = img['src']
                        dicti["picture_link"] = picture_link

                for div in soup2.find_all('div', {"class": 'col-12'}):  # I obtain the european party
                    pol_group = div.find('h3')
                    if pol_group:
                        pol_group = pol_group.text.strip()
                        dicti["European Group"] = pol_group

                    home_group = div.find('div', {"class": 'erpl_title-h3 mt-1 mb-1'})
                    if home_group:
                        home_group = home_group.text.strip()  # I obtain the national party + country (will separate them later)
                        dicti["national"] = home_group

                if "national" not in dicti:
                    dicti["national"] = np.NaN
                if "European Group" not in dicti:
                    dicti["European Group"] = np.NaN
                if "picture_link" not in dicti:
                    dicti["picture_link"] = np.NaN

                dicti = pd.DataFrame([dicti])
                total_df = pd.concat([total_df , dicti], ignore_index=True)

    total_df['Country'] = total_df['national'].str.extract(r'\((.*?)\)', expand=True)
    total_df = total_df.drop(['national'], axis=1)

    return total_df


def add_scraped_info(df: pd.DataFrame,
                     url: str = 'https://www.europarl.europa.eu/meps/en/directory/all/all') -> pd.DataFrame:
    """
    Adds new column containing differences in original and amended text. Joins df and scraped info.
    :param df: df obtained through clean_df
    :param url: mep directory url
    :return:
    """
    df = find_differences(df=df)
    scraped_df = scrape_info(df=df, url=url)
    scraped_df = scraped_df.drop(['picture_link'], axis = 1)
    df_total = df.merge(scraped_df, how='left', on='MEP')

    return df_total

def add_scraped_info_no_diff(df: pd.DataFrame,
                     url: str = 'https://www.europarl.europa.eu/meps/en/directory/all/all') -> pd.DataFrame:
    """
    Joins df and scraped info.
    :param df: df obtained through clean_df
    :return:
    """
    scraped_df = scrape_info(df=df, url=url)
    scraped_df = scraped_df.drop(['picture_link'], axis = 1)
    df_total = df.merge(scraped_df, how='left', on='MEP')

    return df_total