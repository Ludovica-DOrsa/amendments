from __future__ import annotations
import pandas as pd
import requests
import fitz
import urllib.request
import re
from unidecode import unidecode
import numpy as np

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
                        text = unidecode(span['text']) #
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

    # Forward fill amendment number
    df['am_no'] = df['am_no'].ffill()

    # Get max x of text proposed by the commission
    df['xmax_comm'] = np.where((df['text'] == 'Text proposed by the Commission')|
                               (df['text'] == 'Motion for a resolution'), df['xmax'], np.NaN)
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

    return df_total




