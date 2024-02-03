from __future__ import annotations
import pandas as pd
import requests
import fitz
import urllib.request
import re
import numpy as np
import dash_cytoscape as cyto
from bs4 import BeautifulSoup
import difflib
import urllib
import os
import pathlib
import time
from typing import Tuple
from datetime import timedelta
from sklearn.decomposition import NMF
from sklearn.feature_extraction.text import TfidfVectorizer

url = 'https://www.europarl.europa.eu/doceo/document/ITRE-AM-746920_EN.pdf'


def max_idx(nestedlist):
    """
    Get the index of the maximum number in a nested list
    :param nestedlist: the nested list
    :return:
    """
    m = []
    for i in nestedlist:
        m.append(np.argmax(i))
    return pd.Series(m)


def add_topics(df_total: pd.DataFrame,
               n_features: int = 1000,
               n_components: int = 10) -> Tuple[pd.DataFrame, object]:
    """
    Uses negative matrix factorization for topic modelling. Returns the original dataframe with an additional
    column specifying the most probable topic and the nmf model.
    :param n_components: number of topics
    :param df_total: dataframe with a column called Amendment
    :param n_features: build a vocabulary that only consider the top n_features ordered by term frequency across the
    corpus.
    :return:
    """
    tfidf_vectorizer = TfidfVectorizer(max_df=0.95, min_df=2, max_features=n_features,
                                       stop_words="english", token_pattern=r'(?u)\b[A-Za-z]+\b')
    tfidf = tfidf_vectorizer.fit_transform(df_total['Amendment'])
    nmf = NMF(random_state=1, l1_ratio=.5, init='nndsvd', n_components=n_components).fit(tfidf)
    doc_topic_distrib = nmf.transform(tfidf)
    df_total['Topic'] = max_idx(doc_topic_distrib)
    return df_total, nmf


def save_pdf(url: str, name: str | None = None):
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
    start = time.time()
    doc = fitz.open(path)  # Open pdf
    end = time.time()
    print('get_scanned_pdf: fitz.open: ', timedelta(seconds=end - start))

    start = time.time()
    block_dict = {}
    page_num = 1
    for page in doc:  # Iterate all pages in the document
        file_dict = page.get_text('dict')  # Get the page dictionary
        block = file_dict['blocks']  # Get the block information
        block_dict[page_num] = block  # Store in block dictionary
        page_num += 1  # Increase the page value by 1
    end = time.time()
    print('get_scanned_pdf: store blocks: ', timedelta(seconds=end - start))

    start = time.time()
    rows = [
        (
            xmin, ymin, xmax, ymax, text,
            True if "bold" in span_font.lower() else False,
            True if re.sub("[\(\[].*?[\)\]]", "", text).isupper() else False,
            span_font, font_size
        )
        for page_num, blocks in block_dict.items()
        for block in blocks
        if block['type'] == 0
        for line in block['lines']
        for span in line['spans']
        if (text := span['text'].strip()) != ""
        for xmin, ymin, xmax, ymax in [list(span['bbox'])]  # Get bounding box measurements
        for span_font, font_size in [(span['font'], span['size'])]
    ]

    span_df = pd.DataFrame(rows, columns=['xmin', 'ymin', 'xmax', 'ymax',
                                          'text', 'is_upper', 'is_bold',
                                          'span_font', 'font_size'])
    end = time.time()
    print('get_scanned_pdf: Iterate over blocks and pages: ', timedelta(seconds=end - start))
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

    # Only keep digits
    df['am_no'] = df['am_no'].str.replace(r'\D', '', regex=True)
    df['am_no'] = df['am_no'].str.replace(' ', '', regex=False)
    # The row below the amendment number contains MEP names
    df['meps'] = np.where(df['am_no'].shift(1).isna() == False, df['text'], np.NaN)

    # Occasionally the rows below also contain MEP names.
    # If the row above contains MEP names and the current does not contain
    # "Proposal for a regulation/directive/decision/resolution",
    # it also contains MEP names
    df['meps'] = np.where((df['meps'].shift(1).isna() == False) &  # Previous row contains meps
                          ((df['text'].str.contains(
                              r'((\bProposal\b)|(\bMotion\b)) for a ((\bregulation\b)|(\bdirective\b)|(\bdecision\b)|(\bresolution\b))',
                              regex=True, na=False) == False)),
                          # does not contain "Proposal for a regulation"
                          df['text'], df['meps'])

    df = df[df['meps'] != ' ']

    # Forward fill amendment number
    df['am_no'] = df['am_no'].ffill()

    # Get max x of text proposed by the commission
    df['xmax_comm'] = np.where((df['text'] == 'Text proposed by the Commission') |
                               (df['text'] == 'Motion for a resolution') |
                               (df['text'] == 'Draft opinion') |
                               (df['text'] == 'Present text'), df['xmax'], np.NaN)
    df['xmax_comm'] = df.groupby('am_no')['xmax_comm'].ffill()
    # all text with xmin < xmax_comm is text proposed by the commission
    df['type'] = np.where(df['xmin'] < df['xmax_comm'], 'Text proposed by the Commission', np.NaN)
    # all text with xmin > xmax_comm is amendment text
    df['type'] = np.where(df['xmin'] > df['xmax_comm'], 'Amendment', df['type'])

    # Get article (the row below "Proposal for a regulation/directive/decision/resolution")
    # ((\bregulation\b)|(\bdirective\b)|(\bdecision\b)|(\bresolution\b))
    df['article'] = np.where((df['text'].shift() == 'Proposal for a regulation') |
                             (df['text'].shift() == 'Proposal for a directive') |
                             (df['text'].shift() == 'Proposal for a decision') |
                             (df['text'].shift() == 'Proposal for a resolution') |
                             (df['text'].shift() == 'Motion for a resolution') |
                             (df['text'].shift() == 'Draft opinion')
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


def find_differences(df: pd.DataFrame) -> pd.DataFrame:
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
                        # x = f'<del>{a[i1:i2]}</del>'
                        x = f"<span style ='color: #d9230f'>{a[i1:i2]}</span>"
                        new_text = new_text + x
                        # y = f'<ins>{b[j1:j2]}</ins>'
                        y = f"<span style ='color: #139418'>{b[j1:j2]}</span>"
                        new_text = new_text + y
                    if tag == 'delete':
                        # x = f'<del>{a[i1:i2]}</del>'
                        x = f"<span style ='color: #d9230f'>{a[i1:i2]}</span>"
                        new_text = new_text + x
                    if tag == 'insert':
                        # x = f'<ins>{b[j1:j2]}</ins>'
                        x = f"<span style ='color: #139418'>{b[j1:j2]}</span>"
                        new_text = new_text + x
                    if tag == 'equal':
                        # x = f'{a[i1:i2]}'
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
    subdf = subdf.groupby('am_no', as_index=False).agg({'justification': ' '.join})
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

    df_total = df_total.drop(['nan'], axis=1)
    df_total = df_total[df_total['meps'] != ""]
    df_total = df_total[df_total['meps'] != "Draft opinion"]
    df_total = df_total[df_total["meps"].str.contains(fr'\b\s\b', regex=True, case=False)]
    df_total = df_total[-df_total["meps"].str.contains('Compromise amendment', regex=False, case=False)]

    df_total['Amendment'] = df_total['Amendment'].str.removesuffix('Justification')
    df_total['Amendment'] = df_total['Amendment'].str.removeprefix('Amendment')
    df_total['Amendment'] = df_total['Amendment'].str.removeprefix('Draft opinion')
    df_total['Text proposed by the Commission'] = df_total['Text proposed by the Commission'].str.removeprefix(
        'Text proposed by the Commission')
    df_total['Text proposed by the Commission'] = df_total['Text proposed by the Commission'].str.removeprefix(
        'Motion for a resolution')
    df_total['Text proposed by the Commission'] = df_total['Text proposed by the Commission'].str.removeprefix(
        'Draft opinion')

    return df_total


def get_network_elements(df: pd.DataFrame) -> list:
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
            # edges_df = edges_df.append(meplist, ignore_index=True)
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


def get_network_elements_v2(df: pd.DataFrame) -> list:
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
            # edges_df = edges_df.append(meplist, ignore_index=True)
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
        # img_url = df[df['MEP']==mep]['picture_link'].iloc[0]
        d = {'classes': 'nopic', 'data': {'id': mep_id, 'label': mep}, 'position': {'x': 75, 'y': 75}}
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
    soup = BeautifulSoup(html, features="html.parser")

    total_data = []

    for mep in df['MEP'].unique():
        dicti = {"MEP": mep}

        img = soup.find("img", {"alt": re.compile(f"{mep}", re.I)})
        if img:
            x = img.parent.parent.parent.parent
            if x:
                href = x['href']
                webpage2 = requests.get(href)
                soup2 = BeautifulSoup(webpage2.text, features="html.parser")

                span = soup2.find("span", {"class": 'erpl_newshub-photomep'})
                img = span.find("img") if span else None

                dicti["picture_link"] = img['src'] if img else np.NaN

                div = soup2.find_all('div', {"class": 'col-12'})
                for div_item in div:
                    pol_group = div_item.find('h3')
                    home_group = div_item.find('div', {"class": 'erpl_title-h3 mt-1 mb-1'})

                    if pol_group:
                        dicti["European Group"] = pol_group.text.strip()
                    if home_group:
                        dicti["national"] = home_group.text.strip()

                total_data.append(dicti)

    total_df = pd.DataFrame(total_data)
    total_df['Country'] = total_df['national'].str.extract(r'\((.*?)\)', expand=True)
    total_df.drop(['national'], axis=1, inplace=True)

    return total_df


def add_scraped_info(df: pd.DataFrame,
                     url: str = 'https://www.europarl.europa.eu/meps/en/directory/all/all') -> pd.DataFrame:
    """
    Adds new column containing differences in original and amended text. Joins df and scraped info.
    :param df: df obtained through clean_df
    :param url: mep directory url
    :return:
    """
    start = time.time()
    df = find_differences(df=df)
    end = time.time()
    print('add_scraped_info: find_differences: ', timedelta(seconds=end - start))

    start = time.time()
    scraped_df = scrape_info(df=df, url=url)
    end = time.time()
    print('add_scraped_info: scrape_info: ', timedelta(seconds=end - start))

    start = time.time()
    # scraped_df = scraped_df.drop(['picture_link'], axis = 1)
    df_total = df.merge(scraped_df, how='left', on='MEP')
    end = time.time()
    print('df.merge: scrape_info: ', timedelta(seconds=end - start))
    return df_total


def add_scraped_info_no_diff(df: pd.DataFrame,
                             url: str = 'https://www.europarl.europa.eu/meps/en/directory/all/all') -> pd.DataFrame:
    """
    Joins df and scraped info.
    :param url:
    :param df: df obtained through clean_df
    :return:
    """
    start = time.time()
    scraped_df = scrape_info(df=df, url=url)
    end = time.time()
    print('add_scraped_info_no_diff: scrape_info: ', timedelta(seconds=end - start))

    start = time.time()
    scraped_df = scraped_df.drop(['picture_link'], axis=1)
    df_total = df.merge(scraped_df, how='left', on='MEP')
    end = time.time()
    print('add_scraped_info_no_diff: drop&merge: ', timedelta(seconds=end - start))
    return df_total
