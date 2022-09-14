#######################################################
# This app is a pass-through API for submitting tomographic reconstructions for batch job submission at NERSC. 
# The SCRIPT variable outlines the job script that will be submitted.
# The SUPERAPI_URL is the current superfacility API supported by NERSC.
# The SYSTEM is defaulted to Perlmutter.
# 
#######################################################

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import pickle
import requests
import json
import time


SCRIPT = '''#!/bin/bash
#SBATCH -q regular
#SBATCH -A als_g
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -C gpu
#SBATCH -c 64
#SBATCH -G 4
#SBATCH --time=03:00:00
#SBATCH -J tomopy
#SBATCH --exclusive

export NUMEXPR_MAX_THREADS=999
module load python
module load cudatoolkit
source activate tomopy_als

python /global/cfs/cdirs/m1759/lgupta/recon-forOnline-ALS.py '''


SUPERAPI_URL="https://api.nersc.gov/api/v1.2"
SYSTEM = "perlmutter"
TIME_TO_SLEEP = 15 #time in seconds to wait until asking for the task info
PATHS = []

### Instantiate the application
app = FastAPI()

class TomoInputs(BaseModel):
    '''
    The model which expects a data string and a jwt (generated for a Spin client). 
    The types are shown, with no defaults supplied.
    '''
    data: str = Field(..., description="Encoded dictionary containing tomopy inputs")
    jwt: str = Field(..., description="jwt")
    
class TaskInfo(BaseModel):
    '''
    The model which the Task ID generated by the SF API, as a string, and a
    jwt (generated for a Spin client).
    The types are shown, with no defaults supplied.
    '''
    task_id: str = Field(..., description="Task ID")
    jwt: str = Field(..., description="jwt")

class PathInfo(BaseModel):
    path: str = Field(...,description="Encoded dictionary containing tomopy path inputs")
    jwt: str = Field(...,description="jwt")

    
STORE_INPUT_DICTIONARY = {}
## Need a default dictionary.

@app.post("/inputs/")
async def submit_main_job(inputs: TomoInputs):
    '''
    The TomoInputs model is named inputs, and each field is accessed like a python object attribute: 
    data: inputs.data (str)
    jwt: inputs.jwt (str)
    
    The encoded dictionary (already handled before submission) is 
    '''
    
    dict_from_ALS = inputs.data
    STORE_INPUT_DICTIONARY["current"] = dict_from_ALS
    
    job_script = SCRIPT + dict_from_ALS
    submit = requests.post(SUPERAPI_URL+"/compute/jobs/"+SYSTEM, data = {"job": job_script, "isPath": False, "machine": SYSTEM}, headers = {"Authorization": f"Bearer {inputs.jwt}"})
    out = submit.json()
    print(json.dumps(out, indent = 2), flush = True)
    
    time.sleep(TIME_TO_SLEEP)
    r = requests.get(SUPERAPI_URL+"/tasks/"+out["task_id"], headers = {"Authorization": f"Bearer {inputs.jwt}"})
    r = r.json()
    print(json.dumps(r, indent = 2), flush = True)
    return {"task_id": out["task_id"]}

@app.get("/tasks/{task_id}")
async def return_task_status(task_id, jwt):
    ## 
    resp = requests.get(SUPERAPI_URL+"/tasks/"+task_id, headers = {"Authorization": f"Bearer {jwt}"})
    r = resp.json()
    print(json.dumps(r, indent = 2), flush = True)
    if not resp.ok :
        raise HTTPException(status_code = resp.status_code, detail = resp.text)
    return {"return": r}


# @app.post("/file_received/")
# async def file_received(info):
#     PATHS.append(info)

    
# @app.post("/clear_paths/")
# async def clear_paths():
#     PATHS = []
    
# def set_up_new_paths(path, keys = ["inputPath", "filename", "fulloutputPath", "outputFilename"]):
#     d = STORE_INPUT_DICTIONARY["current"]
#     for k in keys:
#         d[k] = inputs.path[k]
#     return d
    
def start_recon(updated_dict):
    job_script = SCRIPT + updated_dict
    submit = requests.post(SUPERAPI_URL+"/compute/jobs/"+SYSTEM, data = {"job": job_script, "isPath": False, "machine": SYSTEM}, headers = {"Authorization": f"Bearer {inputs.jwt}"})
    out = submit.json()
    print(json.dumps(out, indent = 2), flush = True)
    
    time.sleep(TIME_TO_SLEEP)
    r = requests.get(SUPERAPI_URL+"/tasks/"+out["task_id"], headers = {"Authorization": f"Bearer {inputs.jwt}"})
    r = r.json()
    print(json.dumps(r, indent = 2), flush = True)
    print("Automated job started")
    return {"task_id": out["task_id"]}
    
    

    
# def watch_for_file(inputs: PathInfo, sleep = TIME_TO_SLEEP):
#     #current includes the most basic method of limiting endless loop
#     status = "ERROR"
#     count = 0
    
#     string = inputs.path
#     settings = pickle.loads(base64.b64decode(string.encode('utf-8')))
#     FILE = settings["inputPath"] + settings["filename"]
#     print("Looking on " + SYSTEM +" for file "+FILE)
    
#     while status == "ERROR" and count < 100:
#         time.sleep(sleep)
#         r = requests.get(SUPERAPI_URL+"/ls/"+SYSTEM+FILE, headers = {"Authorization": f"Bearer {inputs.jwt}"})
#         out = r.json()
#         status = out["status"]
#         if status == "OK":
#             ready = True
#             break
#         count += 1
            
#     if count == 100: 
#         ready = False
        
#     return ready