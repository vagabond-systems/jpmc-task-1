################################################################################
#
#  Permission is hereby granted, free of charge, to any person obtaining a
#  copy of this software and associated documentation files (the "Software"),
#  to deal in the Software without restriction, including without limitation
#  the rights to use, copy, modify, merge, publish, distribute, sublicense,
#  and/or sell copies of the Software, and to permit persons to whom the
#  Software is furnished to do so, subject to the following conditions:
#
#  The above copyright notice and this permission notice shall be included in
#  all copies or substantial portions of the Software.
#
#  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
#  OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
#  AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
#  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
#  FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
#  DEALINGS IN THE SOFTWARE.

import csv
# from BaseHTTPServer import BaseHTTPRequestHandler,HTTPServer
import http.server
import json
import operator
import os.path
import re
import threading
from datetime import timedelta, datetime
# from itertools import izip
from random import normalvariate, random
from socketserver import ThreadingMixIn

import dateutil.parser

################################################################################
#
# Config

# Sim params

REALTIME = True
SIM_LENGTH = timedelta(days=365 * 5)
MARKET_OPEN = datetime.today().replace(hour=0, minute=30, second=0)

# Market parms
#       min  / max  / std
SPD = (2.0, 6.0, 0.1)
PX = (60.0, 150.0, 1)
FREQ = (12, 36, 50)

# Trades

OVERLAP = 4


################################################################################
#
# Test Data

def bwalk(min, max, std):
    """ Generates a bounded random walk. """
    rng = max - min
    while True:
        max += normalvariate(0, std)
        yield abs((max % (rng * 2)) - rng) + min


def market(t0=MARKET_OPEN):
    """ Generates a random series of market conditions,
        (time, price, spread).
    """
    for hours, px, spd in zip(bwalk(*FREQ), bwalk(*PX), bwalk(*SPD)):
        yield t0, px, spd
        t0 += timedelta(hours=abs(hours))


def orders(hist):
    """ Generates a random set of limit orders (time, side, price, size) from
        a series of market conditions.
    """
    for t, px, spd in hist:
        stock = 'ABC' if random() > 0.5 else 'DEF'
        side, d = ('sell', 2) if random() > 0.5 else ('buy', -2)
        order = round(normalvariate(px + (spd / d), spd / OVERLAP), 2)
        size = int(abs(normalvariate(0, 100)))
        yield t, stock, side, order, size


################################################################################
#
# Order Book

def add_book(book, order, size, _age=10):
    """ Add a new order and size to a book, and age the rest of the book. """
    yield order, size, _age
    for o, s, age in book:
        if age > 0:
            yield o, s, age - 1


def clear_order(order, size, book, op=operator.ge, _notional=0):
    """ Try to clear a sized order against a book, returning a tuple of
        (notional, new_book) if successful, and None if not.  _notional is a
        recursive accumulator and should not be provided by the caller.
    """
    (top_order, top_size, age), tail = book[0], book[1:]
    if op(order, top_order):
        _notional += min(size, top_size) * top_order
        sdiff = top_size - size
        if sdiff > 0:
            return _notional, list(add_book(tail, top_order, sdiff, age))
        elif len(tail) > 0:
            return clear_order(order, -sdiff, tail, op, _notional)


def clear_book(buy=None, sell=None):
    """ Clears all crossed orders from a buy and sell book, returning the new
        books uncrossed.
    """
    while buy and sell:
        order, size, _ = buy[0]
        new_book = clear_order(order, size, sell)
        if new_book:
            sell = new_book[1]
            buy = buy[1:]
        else:
            break
    return buy, sell


def order_book(orders, book, stock_name):
    """ Generates a series of order books from a series of orders.  Order books
        are mutable lists, and mutating them during generation will affect the
        next turn!
    """
    for t, stock, side, order, size in orders:
        if stock_name == stock:
            new = add_book(book.get(side, []), order, size)
            book[side] = sorted(new, reverse=side == 'buy', key=lambda x: x[0])
        bids, asks = clear_book(**book)
        yield t, bids, asks


################################################################################
#
# Test Data Persistence

def generate_csv():
    """ Generate a CSV of order history. """
    with open('test.csv', 'wb') as f:
        writer = csv.writer(f)
        for t, stock, side, order, size in orders(market()):
            if t > MARKET_OPEN + SIM_LENGTH:
                break
            writer.writerow([t, stock, side, order, size])


def read_csv():
    """ Read a CSV or order history into a list. """
    with open('test.csv', 'rt') as f:
        for time, stock, side, order, size in csv.reader(f):
            yield dateutil.parser.parse(time), stock, side, float(order), int(size)


################################################################################
#
# Server

class ThreadedHTTPServer(ThreadingMixIn, http.server.HTTPServer):
    """ Boilerplate class for a multithreaded HTTP Server, with working
        shutdown.
    """
    allow_reuse_address = True

    def shutdown(self):
        """ Override MRO to shutdown properly. """
        self.socket.close()
        http.server.HTTPServer.shutdown(self)


def route(path):
    """ Decorator for a simple bottle-like web framework.  Routes path to the
        decorated method, with the rest of the path as an argument.
    """

    def _route(f):
        setattr(f, '__route__', path)
        return f

    return _route


def read_params(path):
    """ Read query parameters into a dictionary if they are parseable,
        otherwise returns None.
    """
    query = path.split('?')
    if len(query) > 1:
        query = query[1].split('&')
        return dict(map(lambda x: x.split('='), query))


def get(req_handler, routes):
    """ Map a request to the appropriate route of a routes instance. """
    for name, handler in routes.__class__.__dict__.items():
        if hasattr(handler, "__route__"):
            if None != re.search(handler.__route__, req_handler.path):
                req_handler.send_response(200)
                req_handler.send_header('Content-Type', 'application/json')
                req_handler.send_header('Access-Control-Allow-Origin', '*')
                req_handler.end_headers()
                params = read_params(req_handler.path)
                data = json.dumps(handler(routes, params)) + '\n'
                req_handler.wfile.write(bytes(data, encoding='utf-8'))
                return


def run(routes, host='0.0.0.0', port=8080):
    """ Runs a class as a server whose methods have been decorated with
        @route.
    """

    class RequestHandler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args, **kwargs):
            pass

        def do_GET(self):
            get(self, routes)

    server = ThreadedHTTPServer((host, port), RequestHandler)
    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()
    print('HTTP server started on port 8080')
    while True:
        from time import sleep
        sleep(1)
    server.shutdown()
    server.start()
    server.waitForThread()


################################################################################
#
# App

ops = {
    'buy': operator.le,
    'sell': operator.ge,
}


class App(object):
    """ The trading game server application. """

    def __init__(self):
        self._book_1 = dict()
        self._book_2 = dict()
        self._data_1 = order_book(read_csv(), self._book_1, 'ABC')
        self._data_2 = order_book(read_csv(), self._book_2, 'DEF')
        self._rt_start = datetime.now()
        self._sim_start, _, _ = next(self._data_1)
        self.read_10_first_lines()

    @property
    def _current_book_1(self):
        for t, bids, asks in self._data_1:
            if REALTIME:
                while t > self._sim_start + (datetime.now() - self._rt_start):
                    yield t, bids, asks
            else:
                yield t, bids, asks

    @property
    def _current_book_2(self):
        for t, bids, asks in self._data_2:
            if REALTIME:
                while t > self._sim_start + (datetime.now() - self._rt_start):
                    yield t, bids, asks
            else:
                yield t, bids, asks

    def read_10_first_lines(self):
        for _ in iter(range(10)):
            next(self._data_1)
            next(self._data_2)

    @route('/query')
    def handle_query(self, x):
        """ Takes no arguments, and yields the current top of the book;  the
            best bid and ask and their sizes
        """
        try:
            t1, bids1, asks1 = next(self._current_book_1)
            t2, bids2, asks2 = next(self._current_book_2)
        except Exception as e:
            print("error getting stocks...reinitalizing app")
            self.__init__()
            t1, bids1, asks1 = next(self._current_book_1)
            t2, bids2, asks2 = next(self._current_book_2)
        t = t1 if t1 > t2 else t2
        print('Query received @ t%s' % t)
        return [{
            'id': x and x.get('id', None),
            'stock': 'ABC',
            'timestamp': str(t),
            'top_bid': bids1 and {
                'price': bids1[0][0],
                'size': bids1[0][1]
            },
            'top_ask': asks1 and {
                'price': asks1[0][0],
                'size': asks1[0][1]
            }
        },
            {
                'id': x and x.get('id', None),
                'stock': 'DEF',
                'timestamp': str(t),
                'top_bid': bids2 and {
                    'price': bids2[0][0],
                    'size': bids2[0][1]
                },
                'top_ask': asks2 and {
                    'price': asks2[0][0],
                    'size': asks2[0][1]
                }
            }]


################################################################################
#
# Main

if __name__ == '__main__':
    if not os.path.isfile('test.csv'):
        print("No data found, generating...")
        generate_csv()
    run(App())



def class_code_comparision(row):
        if pd.notnull(row["RETN_CLS_MV"]):
            if isinstance(row["RETN_CLS_MV"], str) and isinstance(
                row["RCRD_CLS_CD"], str
            ):
                datafit_class_codes = row["RETN_CLS_MV"].split(",")
                data_aset_inv_class_codes = row["RCRD_CLS_CD"].split("; ")
                result = bool(set(datafit_class_codes) & set(data_aset_inv_class_codes))
                return "Yes" if result else "No"
            else:
                return "No"
        else:
            return "No"


def appl_lvl_class_code_comparision(group):
        aset_ids_count = list(group["ASET_ID"].values)

        group["AVLB_DATA_STOR_COUNT"] = len(aset_ids_count)
        group["DATA_STOR_COUNT_WITH_MATCHING_CLS_CD"] = (
            group["CLS_CD_COMPARISION_IND"].eq("Yes").sum()
        )
        group["DATA_STOR_COUNT_WITH_NOT_MATCHING_CLS_CD"] = (
            group["CLS_CD_COMPARISION_IND"].eq("No").sum()
        )

        if "No" in list(group["DATA_STOR_HAS_CLS_CD"].values):
            group["APPL_LVL_CLS_CD_COMP_IND"] = False
        else:
            # Check if RCRD_CLS_CD is valid for comparision
            group["VLD_RCRD_CLS_CD"] = group["DATA_STOR_HAS_CLS_CD"] == "Yes"
            # Filter the group to only include the rows with not-null record class codes
            filtered_group = group[group["VLD_RCRD_CLS_CD"]]
            if filtered_group.empty:
                # A new column indicating if all the RCRD_CLS_CD match the RETN_CLS_MV
                group["APPL_LVL_CLS_CD_COMP_IND"] = False
            else:
                try:
                    all_record_class_match = (
                        filtered_group["RCRD_CLS_CD"]
                        .isin(filtered_group["RETN_CLS_MV"])
                        .all()
                    )
                    # A new column indicating if all the RCRD_CLS_CD match the RETN_CLS_MV
                    group["APPL_LVL_CLS_CD_COMP_IND"] = all_record_class_match
                except Exception as e:
                    current_app.logger.error(
                        "Error occured while executing the function for {0} with error {1}".format(
                            group["APPL_SYS_ID"], str(e)
                        )
                    )
            group = group.drop("VLD_RCRD_CLS_CD", axis=1)
        match_map = {True: "Yes", False: "No"}
        group["APPL_LVL_CLS_CD_COMP_IND"] = group["APPL_LVL_CLS_CD_COMP_IND"].map(
            match_map
        )
        return group



from reports.core.report import baseReport
from reports.data_pipeline_report.config import reportConfig
from flask import Blueprint, request, current_app
from datetime import datetime, timedelta
from itertools import permutations

import pandas as pd

DELIM = ','

data_pipeline_report_app = Blueprint('data_pipeline_report', __name__)

class DataPipelineReport(baseReport):

    def __init__(self, request):
        super().__init__(request)

    def get_report_config(self):
        """
        """
        self.report_config = reportConfig()

    @staticmethod
    def flatten_seal_data(df):
        seal_data_dict = {}
        json_records = df.to_dict('records')
        for record in json_records:
            seal_data_dict[int(record['APPL_SYS_ID'])] = record
        return seal_data_dict

    @staticmethod
    def flatten_src_appl_seal_data(seal_ids_values_list, seal_data_dict):
        data_dict_list = []
        for src_appl_sys_id in seal_ids_values_list:
            appl_sys_nm, tech_grp_nm = [], []
            if src_appl_sys_id:
                for app_sys_id in src_appl_sys_id.split(','):
                    app_sys_id = int(app_sys_id) if app_sys_id.isnumeric() else None
                    if app_sys_id and app_sys_id in seal_data_dict:
                        seal_data_obj = seal_data_dict[app_sys_id]
                        appl_sys_nm.append(seal_data_obj['APPL_SYS_NM'])
                        tech_grp_nm.append(seal_data_obj['APPL_TECH_GP_OWNR_NM'])
            data_dict_list.append({
                "PPLN_SRC_APPL_SYS_MV" : src_appl_sys_id,
                "SRC_APPL_SYS_NM": DELIM.join(appl_sys_nm),
                "SRC_APPL_TECH_GP_OWNR_NM" : DELIM.join(tech_grp_nm)
                })
        return pd.DataFrame(data_dict_list)

    @staticmethod
    def flatten_ownr_appl_seal_data(seal_ids_values_list, seal_data_dict):
        data_dict_list = []
        for ownr_appl_sys_id in seal_ids_values_list:
            appl_sys_nm, tech_grp_nm, lob_cd = [], [], []
            appl_ownr_sid, info_ownr_sid, cto_sid = [], [], []
            if ownr_appl_sys_id:
                for app_sys_id in ownr_appl_sys_id.split(','):
                    app_sys_id = int(app_sys_id) if app_sys_id.isnumeric() else None
                    if app_sys_id and app_sys_id in seal_data_dict:
                        seal_data_obj = seal_data_dict[int(app_sys_id)]
                        appl_sys_nm.append(seal_data_obj['APPL_SYS_NM'])
                        tech_grp_nm.append(seal_data_obj['APPL_TECH_GP_OWNR_NM'])
                        appl_ownr_sid.append(seal_data_obj['APPL_OWNR_SID'])
                        info_ownr_sid.append(seal_data_obj['INFO_OWNR_SID'])
                        cto_sid.append(seal_data_obj['CTO_SID'])
                        lob_cd.append(seal_data_obj['APPL_LOB_CD'])
            data_dict_list.append({
                "PPLN_OWNR_APPL_SYS_MV" : ownr_appl_sys_id,
                "OWNR_APPL_SYS_NM": DELIM.join(appl_sys_nm),
                "OWNR_APPL_TECH_GP_OWNR_NM" : DELIM.join(tech_grp_nm),
                "OWNR_APPL_OWNR_SID" : DELIM.join(appl_ownr_sid),
                "OWNR_INFO_OWNR_SID" : DELIM.join(info_ownr_sid),
                "OWNR_CTO_SID" : DELIM.join(cto_sid),
                "OWNR_APPL_LOB_CD" : DELIM.join(lob_cd)
                })
        return pd.DataFrame(data_dict_list)

    @staticmethod
    def flatten_ppln_ownr_appl_sys_mv(df):
        temp_list = []
        data_columns = df.columns
        json_records = df.to_dict('records')
        ### "PPLN_OWNR_APPL_SYS_MV":"89955","PPLN_ownr_APPL_SYS_MV":null
        for record in json_records:
            ownr_appl_sys_id = record['PPLN_OWNR_APPL_SYS_MV']
            del record['PPLN_OWNR_APPL_SYS_MV']
            for app_sys_id in ownr_appl_sys_id.split(','):
                temp_dict = record.copy()
                if app_sys_id.isnumeric():
                    temp_dict.update({
                        "APPL_SYS_ID": int(app_sys_id),
                        })
                    temp_list.append(temp_dict)

        return pd.DataFrame(temp_list)

    @staticmethod
    def get_file_tdq_ovrd_in_cnts(df):
        combined_list = []
        for record in df.to_dict(orient="records"):
            if record['CNT_Y'] > 0 and record['CNT_N'] > 0 :
                for item in ['N', 'Y']:
                    temp_record = record.copy()
                    temp_record['OVRD_IN'] = item
                    combined_list.append(temp_record)
            else:
                if record['CNT_Y'] > 0:
                    record['OVRD_IN'] = 'Y'
                elif record['CNT_N'] > 0:
                    record['OVRD_IN'] = 'N'
                combined_list.append(record)
        return pd.DataFrame(combined_list)

    @staticmethod
    def get_completeness_indicator(row):
        number_columns = ['RCRD_RCV_NB','RCRD_LD_NB','RCRD_RJCT_NB']
        completeness_in = 'N'
        if row.JOB_EXEC_STS_NM == 'COMPLETED':
            row[number_columns] =  row[number_columns].fillna(0)
            if (row.RCRD_RCV_NB == row.RCRD_LD_NB) and \
                row.RCRD_RJCT_NB == 0:
                return 'Y'
        return completeness_in

    def extract_and_transform(self):
        """
        """
        ###################################### SEAL_ALL_DF #######################################
        SEAL_ALL_DF = self.get_dataframe_from_source("SEAL", "QUERY")
  
        SEAL_DATA_DICT = self.flatten_seal_data(SEAL_ALL_DF)

        RCRD_CLS_MV = ['CONFIG DATA ONLY','DATA IN TRANSIT ONLY','NO JPMC DATA']

        RCRD_CLS_MV_PERMUTATIONS = RCRD_CLS_MV + [" | ".join(item) for item in permutations(RCRD_CLS_MV)]

        FILTERED_SEAL_IDS = SEAL_ALL_DF[(
            (
                SEAL_ALL_DF["APPL_LOB_CD"].isin(['CCB']) | (
                SEAL_ALL_DF["APPL_LOB_CD"].isin(['CT']) & SEAL_ALL_DF['APPL_TECH_GP_OWNR_NM'].isin(['CCB Risk']))
            ) & 
            (
                SEAL_ALL_DF["APPL_SYS_STS_NM"].isin(['Operate','Retired'])
            ) &
            (
                ~SEAL_ALL_DF['OVRL_HOST_TYPE_NM'].isin(['External'])
            ) &
            (
                ~SEAL_ALL_DF['RCRD_CLS_MV'].isin(RCRD_CLS_MV_PERMUTATIONS)
            ) 
        )]['APPL_SYS_ID'].unique()

        ############################### TECH_DATA_QLTY_OVRD_INS_DF ################################        

        TECH_DATA_QLTY_OVRD_INS_DF = self.get_dataframe_from_source("TECH_DATA_QLTY_OVRD_INS", "QUERY")

        TECH_DATA_QLTY_OVRD_INS_DF = self.flatten_ppln_ownr_appl_sys_mv(TECH_DATA_QLTY_OVRD_INS_DF)

        ### filter out LOB SEALS
        TECH_DATA_QLTY_OVRD_INS_DF = TECH_DATA_QLTY_OVRD_INS_DF[
            TECH_DATA_QLTY_OVRD_INS_DF["APPL_SYS_ID"].isin(FILTERED_SEAL_IDS)
        ]

        TECH_DATA_QLTY_OVRD_INS_DF.rename(
            columns={"OWNR_APPL_SYS_MV":"PPLN_OWNR_APPL_SYS_MV"}, 
            inplace=True
            )

        TECH_DATA_QLTY_OVRD_INS_DF = TECH_DATA_QLTY_OVRD_INS_DF.drop_duplicates(subset=['PPLN_ID'])
        
        APPL_TDQ_OVRD_IN_CNTS_DF = TECH_DATA_QLTY_OVRD_INS_DF.copy()

        APP_PPLN_IDS_DF = TECH_DATA_QLTY_OVRD_INS_DF.copy()
         
        del TECH_DATA_QLTY_OVRD_INS_DF["APPL_SYS_ID"]

        ################################# FILE_TDQ_OVRD_IN_CNTS_QUERY #####################################

        APPL_TDQ_OVRD_IN_CNTS_DF['FILE_TDQ_OVRD_IN_Y'] = APPL_TDQ_OVRD_IN_CNTS_DF.apply(
            lambda x : 1 if x['FILE_TECH_DATA_QLTY_OVRD_IN'] == 'Y' else 0, axis=1
        )

        APPL_TDQ_OVRD_IN_CNTS_DF['FILE_TDQ_OVRD_IN_N'] = APPL_TDQ_OVRD_IN_CNTS_DF.apply(
            lambda x : 1 if x['FILE_TECH_DATA_QLTY_OVRD_IN'] != 'Y' else 0, axis=1
        )

        TDQ_OVRD_IN_CNTS_DF = APPL_TDQ_OVRD_IN_CNTS_DF.groupby(["APPL_SYS_ID"]).agg(
            CNT_Y=('FILE_TDQ_OVRD_IN_Y','sum'),
            CNT_N=('FILE_TDQ_OVRD_IN_N','sum'),
            ).reset_index()

        FILE_TDQ_OVRD_IN_CNTS_DF = self.get_file_tdq_ovrd_in_cnts(
            TDQ_OVRD_IN_CNTS_DF
            )

        ################################### MIN_EVT_PBLS_TS_DF ####################################
        
        MIN_EVT_PBLS_TS_DF = self.get_dataframe_from_source("MIN_EVT_PBLS_TS", "QUERY")
        
        MIN_EVT_PBLS_TS_DF = self.flatten_ppln_ownr_appl_sys_mv(MIN_EVT_PBLS_TS_DF)

        MIN_EVT_PBLS_TS_DF = MIN_EVT_PBLS_TS_DF.groupby('APPL_SYS_ID')['EVT_PBLSH_TS'].min().reset_index()

        MIN_EVT_PBLS_TS_DF.rename(columns={"EVT_PBLSH_TS":"MIN_EVT_PBLSH_TS"}, inplace=True)
        
        ### filter out LOB SEALS
        MIN_EVT_PBLS_TS_DF = MIN_EVT_PBLS_TS_DF[
            MIN_EVT_PBLS_TS_DF["APPL_SYS_ID"].isin(FILTERED_SEAL_IDS)
        ]
        
        SEAL_INFO_COPY = SEAL_ALL_DF[["APPL_SYS_ID","APPL_SYS_NM","APPL_TECH_GP_OWNR_NM"]]

        MIN_EVT_PBLS_TS_DF = pd.merge(
            MIN_EVT_PBLS_TS_DF,
            SEAL_INFO_COPY,
            how='left', 
            on='APPL_SYS_ID'
            )

        ## adding CNT_Y and CNT_N columns to MIN_EVT_PBLS_TS
        MIN_EVT_PBLS_TS_DF = pd.merge(
            MIN_EVT_PBLS_TS_DF,
            TDQ_OVRD_IN_CNTS_DF,
            how='left', 
            on='APPL_SYS_ID'
            )

        ################################### DATA_PPLN_TXN_EVT_DF #################################

        DATA_PPLN_TXN_EVT_DF = self.get_dataframe_from_source("DATA_PPLN_TXN_EVT", "QUERY")
        ownr_seal_info_list = DATA_PPLN_TXN_EVT_DF["PPLN_OWNR_APPL_SYS_MV"].unique()
        src_seal_info_list = DATA_PPLN_TXN_EVT_DF["PPLN_SRC_APPL_SYS_MV"].unique()
        OWNR_SEAL_INFO_DF = self.flatten_ownr_appl_seal_data(ownr_seal_info_list, SEAL_DATA_DICT)
        SRC_SEAL_INFO_DF = self.flatten_src_appl_seal_data(src_seal_info_list, SEAL_DATA_DICT)
        DATA_PPLN_TXN_EVT_DF = pd.merge(
            DATA_PPLN_TXN_EVT_DF,
            OWNR_SEAL_INFO_DF,
            how='left', 
            on='PPLN_OWNR_APPL_SYS_MV'
            )
        DATA_PPLN_TXN_EVT_DF = pd.merge(
            DATA_PPLN_TXN_EVT_DF,
            SRC_SEAL_INFO_DF,
            how='left', 
            on='PPLN_SRC_APPL_SYS_MV'
            )
        
        ### filter out FILTERED_SEAL_IDS
        DATA_PPLN_TXN_EVT_DF = DATA_PPLN_TXN_EVT_DF[
            DATA_PPLN_TXN_EVT_DF["PPLN_OWNR_APPL_SYS_MV"].str.contains(
                '|'.join([ str(sid) for sid in FILTERED_SEAL_IDS])
                )
            ]
		
        ### COMPLETENESS_CHECK
        DATA_PPLN_TXN_EVT_DF['COMPLETENESS_IN'] = DATA_PPLN_TXN_EVT_DF.apply(
            self.get_completeness_indicator, axis=1
            )

        DATA_PPLN_TXN_EVT_DF['CORRECTNESS_IN'] = DATA_PPLN_TXN_EVT_DF['COMPLETENESS_IN']

        #################################### APP_PPLN_IDS_DF #####################################

        APP_PPLN_IDS_DF = APP_PPLN_IDS_DF[["APPL_SYS_ID", "PPLN_ID", "FILE_TECH_DATA_QLTY_OVRD_IN"]]

        #################################### LATEST_EVT_TDQ_OVRD_IN_DF #####################################

        LATEST_PPLN_RGST_INFO_DF = self.get_dataframe_from_source("LATEST_PPLN_RGST_INFO", "QUERY")

        LATEST_EVT_TDQ_OVRD_IN_DF = pd.merge(
            LATEST_PPLN_RGST_INFO_DF,
            TECH_DATA_QLTY_OVRD_INS_DF,
            how='left', 
            on='PPLN_ID'
            )

        #################################### SEAL_ELIG_TDQ_DF #####################################

        SEAL_ELIG_TDQ_DF = SEAL_ALL_DF[
            SEAL_ALL_DF["APPL_SYS_ID"].isin([int(i) for i in FILTERED_SEAL_IDS])
        ][
            [
                "APPL_SYS_ID", 
                "APPL_TECH_GP_OWNR_NM", 
                "APPL_SYS_STS_NM", 
                "APPL_LOB_CD",
                "OVRL_HOST_TYPE_NM",
                "RCRD_CLS_MV", 
                "APPL_SYS_NM", 
                "APPL_OWNR_SID"
            ]
        ]

        tables_mapper = {
            "TDQ_OVRD_IN_RPT" : TECH_DATA_QLTY_OVRD_INS_DF,
            "DATA_PPLN_TXN_EVT_RPT": DATA_PPLN_TXN_EVT_DF,
            "MIN_EVT_PBLS_TS_RPT" : MIN_EVT_PBLS_TS_DF,
            "FILE_TDQ_OVRD_IN_CNTS_RPT": FILE_TDQ_OVRD_IN_CNTS_DF,
            "APP_PPLN_IDS_RPT" : APP_PPLN_IDS_DF,
            "SEAL_ELIG_TDQ_RPT": SEAL_ELIG_TDQ_DF,
            "LATEST_EVT_TDQ_OVRD_IN_RPT": LATEST_EVT_TDQ_OVRD_IN_DF
        }
        return tables_mapper

    def generate_report(self):
        """
        """
        try:
            self.get_db_conn()
            self.fetch_report_config_id()
            self.insert_rpt_exec_rec()
            tables_mapper = self.extract_and_transform()
            for table_name, table_dataframe  in tables_mapper.items():
                self.report_config.TRGT_TBL_NM = table_name
                self.rows_count_to_load = self.rows_count_to_load + (table_dataframe.shape)[0]
                result_df = self.generic_dataframe_wrapper(table_dataframe)
                self.load_result_to_table(result_df)
                self.purge_historical_data_from_table()
            self.execution_status = "COMPLETED"
        except Exception as e:
            self.log_report_generation_error(
                self.report_config.RPT_CONFIG_CD, 
                self.exec_id,
                str(e)
            )
            self.execution_status = "ERROR"
        self.update_rpt_exec_rec(self.execution_status, self.rows_count_to_load)
        self.clean_up()
        return self.execution_status

@data_pipeline_report_app.route("/data_pipeline_report")
def data_pipeline_report():
    """
    """
    obj = DataPipelineReport(request)
    execution_status = obj.generate_report()
    if execution_status == "ERROR":
        status_msg, status_code = "Failed while generating report", 500
    else:
        status_msg, status_code = "Successfully generated report", 200
    return status_msg, status_code


