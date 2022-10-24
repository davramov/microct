"""
ALS_batch_recon.py
Functions that used to either set up reconstruction batch jobs, or used within the batch jobs  
"""

import sys
import os
import multiprocessing as mp
os.environ['NUMEXPR_MAX_THREADS'] = str(mp.cpu_count()) # to avoid numexpr warning
import numexpr
import numpy as np
import dxchange
import base64
import pickle
import time
from pathlib import Path

import ALS_recon_functions as als
import ALS_recon_helper as helper

def get_batch_template(algorithm="astra"):
    """ Gets path to appropriate batch scrpit template, depending on whether using Astra or SVMBIR, on Cori or Perlmutter """
    
    s = os.popen("echo $NERSC_HOST")
    out = s.read()
    if algorithm == "svmbir":
        if 'cori' in out:
            return os.path.join('slurm_scripts','svmbir_template_job-cori.txt')
        elif 'perlmutter' in out:
            return os.path.join('slurm_scripts','svmbir_template_job-perlmutter.txt')
        else:
            sys.exit('not on cori or perlmutter -- throwing error')
    if 'cori' in out:
        return os.path.join('slurm_scripts','astra_template_job-cori.txt')
    elif 'perlmutter' in out:
        return os.path.join('slurm_scripts','astra_template_job-perlmutter.txt')
    else:
        sys.exit('not on cori or perlmutter -- throwing error')

def create_batch_script(settings):
    """ Completes batch script from template by adding reconstruction settings """
    
    with open (get_batch_template(), "r") as t:
        template = t.read()

    s = os.popen("echo $USER")
    username = s.read()[:-1]
    user_template = template.replace('<username>',username)
        
    configs_dir = Path(os.path.join(settings["data"]["output_path"],"configs/"))
    if not configs_dir.exists():
        os.mkdir(configs_dir)
       
    config_script_name = os.path.join(configs_dir,"config_"+settings["data"]["name"]+".sh")    
    enc = dictionary_prep(settings)
    with open(config_script_name, 'w') as f:
        script = user_template
        script += "\n"
        # script += "shifter cd " + os.getcwd()
        # script += "\n"
        script += f"shifter python {os.getcwd()}/backend/ALS_batch_recon.py"
        script += " '" + enc + "'"
        f.write(script)
        f.close()
    
    return configs_dir, config_script_name


def dictionary_prep(dictionary):
    ''' Encodes reconstruction parameter dictionary into string 
    Input: 
    dictionary: single dictionary of settings
    Returns 
    st: encoded dictionary
    '''
    pik = pickle.dumps(dictionary, protocol=pickle.HIGHEST_PROTOCOL)
    st = base64.b64encode(pik).decode('utf-8')
    return st


def batch_astra_recon(settings): 
    """ Perform Astra reconstruction using encoded settings string """

    use_gpu = als.check_for_gpu()

    nchunk = 50 
    '''
    nchunk is balance between available cpus and memory (larger value can be more parallelized but uses more memory)
    50 was empirically chosen on Perlmutter exclusive node, though 100 was more or less the same
    ''' 
    save_dir = os.path.join(settings["data"]["output_path"],settings["data"]["name"])
    if not os.path.exists(save_dir): os.makedirs(save_dir)
    save_name = os.path.join(save_dir,settings["data"]["name"])
    
    # if COR is None, use cross-correlation finder
    if settings["recon"]["COR"] is None:
        settings["recon"]["COR"] = als.auto_find_cor(settings["data"]["data_path"])

    for i in range(np.ceil((settings["data"]['stop_slice']-settings["data"]['start_slice'])/nchunk).astype(int)):
        start_iter = settings["data"]['start_slice']+i*nchunk
        stop_iter = np.minimum(start_iter+nchunk,settings["data"]['stop_slice'])
        print(f"Starting recon of slices {start_iter}-{stop_iter}...",end=' ')
        tic = time.time()

        recon, _ = helper.default_reconstruction(path=settings["data"]["data_path"],
                               angles_ind=settings["data"]['angles_ind'],
                               slices_ind=slice(start_iter,stop_iter,1),
                               COR=settings["recon"]["COR"],
                               proj_downsample=settings["data"]["proj_downsample"],
                               fc=settings["recon"]["fc"],
                               preprocessing_settings=settings["preprocess"],
                               postprocessing_settings=settings["postprocess"],
                               use_gpu=use_gpu)

        print(f"Finished: took {time.time()-tic} sec. Saving files...")
        dxchange.write_tiff_stack(recon, fname=save_name, start=start_iter)
    print("Done")
    
def mpi4py_svmbir_recon(settings):
    """ Perform SVMBIR reconstruction using encoded settings string. Parallelize over slices using mpi4py """

    from mpi4py import MPI
    comm = MPI.COMM_WORLD
    size = comm.Get_size()
    rank = comm.Get_rank()
    name = MPI.Get_processor_name()

    # if COR is None, use cross-correlation finder
    if settings["svmbir_settings"]["COR"] is None:
        settings["svmbir_settings"]["COR"] = als.auto_find_cor(settings["data"]["data_path"])    
    
    for i in range((settings["data"]['stop_slice']-settings["data"]['start_slice'])):
        if i % size == rank:
            print(f"Starting slice {i} on {name}, core {rank} of {size}")
            tic = time.time()
            tomo, angles = als.read_data(settings["data"]["data_path"],
                                         proj=settings["data"]["angles_ind"],
                                         sino=slice(i,i+1,1),
                                         downsample_factor=settings["data"]["proj_downsample"],
                                         args=settings["preprocess"])
            svmbir_recon = als.svmbir_recon(tomo,angles,**svmbir_settings)
            print(f"Finished slice {i}, took {time.time()-tic} sec")


def main():
    print(f"Starting ALS_batch_recon")
    tic = time.time()
    string = sys.argv[:][-1] 
    settings = pickle.loads(base64.b64decode(string.encode('utf-8')))
    if 'svmbir_settings' in settings:
        mpi4py_svmbir_recon(settings)
        print(f"SVMBIR...")
    else:
        print(f"Astra...")
        batch_astra_recon(settings)
       
    print(f"Finished ALS_batch_recon, took {time.time()-tic} sec")

    
if __name__ == '__main__':
    main()