import os
import glob
import re
import pprint
import qcodes as qc
import pandas as pd
from typing import Tuple, Optional, Dict, Union, List, Any
from pymongo import collection
import xarray as xr 
from qcodes.dataset.sqlite.database import connect
from qcodes.dataset.database_extract_runs import extract_runs_into_db
from qcodes.dataset.data_set import load_by_id, load_by_guid, DataSet
pp = pprint.PrettyPrinter(indent=4)


class Qdatalib:
    """Class for expporting QCoDeS data stored in SQLite in to other formats 
        and organicing the exported data files using a MongoDB database

    """


    def __init__(self, mongo_collection: collection = None,
                 db_local: str = '',
                 db_shared: str = 'shared.db',
                 lib_dir: str = '.') -> None:
        """[summary]

        :param mongo_collection: The collection where information about the files are stored, defaults to None
        :type mongo_collection: collection, optional
        :param db_local: path to the local QCoDeS SQLite databas, defaults to ''
        :type db_local: str, optional
        :param db_shared: path to shared QCoDeS SQLite database, defaults to 'shared.db'
        :type db_shared: str, optional
        :param lib_dir: path to directory to shared files, defaults to '.'
        :type lib_dir: str, optional
        """
        self.db_local = db_local
        self.db_shared = db_shared
        self.lib_dir = lib_dir
        self.mongo_collection: collection = mongo_collection

    def extract_run_into_db_and_catalog_by_id(self, run_id: int,
                                              scientist: str = 'john doe',
                                              tag: str = '',
                                              note: str = '',
                                              dict_exstra={}) -> None:
        """

        Extract data seleceted by run_id to shared SQLite database
        """

        self.uploade_to_catalog_by_id(run_id,
                                      scientist,
                                      tag,
                                      note,
                                      dict_exstra)

        shared_conn = connect(self.db_shared)
        extract_runs_into_db(self.db_local,  self.db_shared, run_id)
        shared_conn.close()

    def extract_run_into_nc_and_catalog(self, run_id: int,
                                        scientist: str = 'john doe',
                                        tag: str = '',
                                        note: str = '',
                                        dict_exstra={}
                                        ) -> None:
        """

        Extract data seleceted by run_id to shared netcdf file
        """

        self.uploade_to_catalog_by_id(run_id,
                                      scientist,
                                      tag,
                                      note,
                                      dict_exstra)

        data = self.load_by_id_local(run_id)
        x_data = data.to_xarray_dataset()
        nc_path = os.path.join(self.lib_dir, data.guid+".nc")
        x_data.to_netcdf(nc_path)

        return None

    def extract_run_into_csv_and_catalog(self, run_id: int,
                                        scientist: str = 'john doe',
                                        tag: str = '',
                                        note: str = '',
                                        dict_exstra={}
                                        ) -> None:
        """

        Extract data seleceted by run_id to shared csv file
        """

        self.uploade_to_catalog_by_id(run_id,
                                      scientist,
                                      tag,
                                      note,
                                      dict_exstra)

        data = self.load_by_id_local(run_id)
        csv_data = data.to_pandas_dataframe()
        csv_data.reset_index(inplace=True)
        csv_path = os.path.join(self.lib_dir, data.guid+".csv")
        csv_data.to_csv(csv_path)

        return None        

    def uploade_to_catalog_by_id(self,
                                 id: int,
                                 scientist: str = 'john doe',
                                 tag: str = '',
                                 note: str = '',
                                 dict_exstra={}) -> None:
        """

        Upload to catalog
        """

        data = self.load_by_id_local(id)
        original_path = self.db_local 
        file = re.split('/|\\\\', self.db_shared)[-1]
        run_id = data.captured_run_id
        exp_id = data.exp_id
        exp_name = data.exp_name
        run_time = data.run_timestamp()
        sample_name = data.sample_name
        parameters = [(par.name, par.unit) for par in data.get_parameters()]
        post = {"_id": data.guid, 'file': file, original_path: 'original_path', 
                'run_id': run_id,
                'exp_id': exp_id,
                'exp_name': exp_name,
                'run_time': run_time,
                'sample_name': sample_name,
                'parameters': parameters,
                'scientist': scientist,
                'tag': tag,
                'note': note}
        post.update(dict_exstra)
        filter = {"_id": data.guid}
        newvalues = {"$set": post}
        self.mongo_collection.update_one(filter, newvalues, upsert=True)

    def get_data_by_catalog(self, search_digt: Dict[str, Union[str, float]]) -> Union[List, DataSet]:

        results = list(self.mongo_collection.find(search_digt))

        tjek_number_of_results = self.number_of_results(results)

        if tjek_number_of_results[0]:
            return tjek_number_of_results[1]
        else:
            file_path = glob.glob(str(self.lib_dir) + "/**/" + results[0]['file'], recursive = True)
            return self.load_shared(results[0]['_id'], file_path[0])


    def get_data_from_nc_by_catalog(self, search_digt: Dict[str, Union[str, float]]) -> Union[List, Any]:
        results = list(self.mongo_collection.find(search_digt))
        tjek_number_of_results = self.number_of_results(results)

        if tjek_number_of_results[0]:
            return tjek_number_of_results[1]
        else:
            nc_path = glob.glob(str(self.lib_dir) + "/**/" + results[0]['_id']+".nc", recursive = True)
            #nc_path = os.path.join(self.lib_dir, results[0]['_id']+".nc")
            return xr.open_dataset(nc_path[0])

    def get_data_from_csv_by_catalog(self, search_digt: Dict[str, Union[str, float]]) -> Union[List, Any]:
        results = list(self.mongo_collection.find(search_digt))
        tjek_number_of_results = self.number_of_results(results)

        if tjek_number_of_results[0]:
            return tjek_number_of_results[1]
        else:
            csv_path = glob.glob(str(self.lib_dir) + "/**/" + results[0]['_id']+".csv", recursive = True)
            #nc_path = os.path.join(self.lib_dir, results[0]['_id']+".nc")
            return pd.read_csv(csv_path[0], index_col=0)

    def number_of_results(self, results: List) -> Tuple[bool,List]:
        number_of_results = len(results)
        if number_of_results > 10:
            print('The query returned {} results'.format(number_of_results))
            return (True, results)
        elif number_of_results > 1:
            print('The query returend {} results'.format(number_of_results))
            pp.pprint(results)
            return (True, results)
        else:
            return (False, results)

    def load_by_id_local(self, id: int) -> DataSet:

        local_conn = connect(self.db_local)
        data = load_by_id(id,local_conn)
        
        return data

    def load_shared(self, guid: str, db_path: str) -> DataSet:

        #try:
        shared_conn = connect(db_path) # as shared_conn:
        data = load_by_guid(guid, shared_conn)
            
        #finally:
         #   shared_conn.close()
          #  shared_conn = connect(self.db_shared)
            #del shared_conn
        return data
