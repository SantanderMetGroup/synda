#!/usr/bin/env python
# -*- coding: ISO-8859-1 -*-

##################################
#  @program        synda-pp
#  @description    climate models data transfer program
#  @copyright      Copyright “(c)2009 Centre National de la Recherche Scientifique CNRS. 
#                             All Rights Reserved”
#  @license        CeCILL (https://raw.githubusercontent.com/Prodiguer/synda/master/sdp/doc/LICENSE)
##################################

"""Contains events consumer thread."""

import threading
import time
import traceback
import splog
import speventdao
import spppprdao
import spconfig
import sppipelinedep
import spconst
import spdb
from sptypes import PPPRun
import sppostprocessing
from spexception import SPException,PipelineRunningException

def create_pipeline(pipeline,status,e,conn):
    try:
        sppostprocessing.add_ppprun(pipeline,status,e.project,e.model,e.dataset_pattern,e.variable,conn)
        e.status=spconst.EVENT_STATUS_OLD # mark events as done
    except PipelineRunningException, ex: # keep exception instance name as 'ex' not to collide with 'e' event name
        splog.warning('SPEVENTT-012',"Event status set to anomaly")
        e.status=spconst.EVENT_STATUS_ANOMALY # mark events as anomaly (this event has been inhibited and may need to be manually switched to 'new'. also most often it's not necessary (i.e. it has been inhibited because another identical event was preceding it))

def get_pipeline_dependency(name,dataset_pattern,variable,conn):
    pipeline_dependencies=spppprdao.get_pppruns(order='fifo',pipeline=name,dataset_pattern=dataset_pattern,variable=variable,conn=conn)

    if len(pipeline_dependencies)==0:
        return None
    elif len(pipeline_dependencies)==1:
        return pipeline_dependencies[0]
    else:
        assert False # currently, one pipeline can only have one dep max

def consume_events():
    try:
        events=speventdao.get_events(status=spconst.EVENT_STATUS_NEW,limit=20) # process 20 events at a time (arbitrary)
        if len(events)>0:
            try:
                conn=spdb.connect()
                conn.execute('begin immediate') # transaction begin (full db lock)

                for e in events:
                    process_event(e,conn)

                # Check
                # (at this point, all events statuses should be !EVENT_STATUS_NEW)
                li=[e for e in events if e.status in [spconst.EVENT_STATUS_NEW]]
                assert len(li)==0
                
                # Switch processed events status in DB
                splog.info('SPEVENTT-003',"%i event(s) processed"%len(events))
                speventdao.update_events(events,conn)

                conn.commit() # transaction end
            finally:
                spdb.disconnect(conn) # if exception occur, we do the rollback here

    except Exception, e:
        traceback.print_exc(file=open(spconfig.stacktrace_log_file,"a"))

def process_event(e,conn):


    # ignore event based on project

    if e.project not in spconst.AUTHORIZED_PROJECT:
        splog.info('SPEVENTT-024',"Event ignored (%s)"%str(e))
        e.status=spconst.EVENT_STATUS_OLD # mark events as done
        return

    # ignore unknown event

    if e.name not in pipelinedep.event_pipeline_mapping:
        splog.info('SPEVENTT-004',"Ignore event as not declared in spbindings file (%s)"%str(e))
        e.status=spconst.EVENT_STATUS_OLD # mark events as done
        return


    # retrieve the pipeline which is binded to the event

    pipeline_name,start_status=pipelinedep.event_pipeline_mapping[e.name]


    # manage start dependency

    # this is to access the 'trigger' dict from the 'value' side
    reverse_trigger=dict((v[0], (k,v[1])) for k, v in pipelinedep.trigger.iteritems()) # TODO: replace this with a bidirectional dict. Maybe also add loop to allow multiple dependencies.

    if pipeline_name in reverse_trigger:
        splog.info('SPEVENTT-044',"starting dependency exists for this pipeline in configuration file (new_pipeline=%s,dependency=%s)"%(pipeline_name,reverse_trigger[pipeline_name]))

        # retrieve dependency
        start_dependency=reverse_trigger[pipeline_name][0]
        dependency_type=reverse_trigger[pipeline_name][1]

        start_status=get_new_pipeline_status(start_dependency,dependency_type,e,conn) # override 'start_status'
    else:
        start_dependency=None



    # main

    create_pipeline(pipeline_name,start_status,e,conn)

def get_new_pipeline_status(start_dependency,dependency_type,e,conn):


    if dependency_type==spconst.TRIGGER_TYPE_D2NV:
        # N to 1 (memo: works in reverse with D2NV). we want to find one dataset from N var.

        v_='' # unset variable so to match the dataset
    elif dependency_type==spconst.TRIGGER_TYPE_D2D:
        # 1 to 1

        v_=e.variable # default is ok
    elif dependency_type==spconst.TRIGGER_TYPE_NV2D:
        # 1 to N (memo: works in reverse with NV2D). we want to find N var from one dataset.

        # hack: we force status to PAUSE here.
        #
        # The trigger will happen at the end of the last 'variable' pipeline
        # (in postprocessing.job_done func). A better way maybe is to call
        # 'all_variable_complete' func here. Also maybe merging both dep code
        # (in postprocessing.job_done and here) would improve clarity..
        #
        return spconst.PPPRUN_STATUS_PAUSE


    pipeline_dependency=get_pipeline_dependency(start_dependency,e.dataset_pattern,v_,conn) # retrieve dependency
    if pipeline_dependency is not None:
        splog.info('SPEVENTT-046',"dependency found in ppprun table (dependency=%s)"%(start_dependency,))
        if pipeline_dependency.status==spconst.PPPRUN_STATUS_DONE:
            splog.info('SPEVENTT-048',"Create with WAITING status as dependent pipeline is done (dependency=%s,dataset_pattern=%s,variable=%s)"%(start_dependency,e.dataset_pattern,e.variable))
            status=spconst.PPPRUN_STATUS_WAITING
        else:
            splog.info('SPEVENTT-010','Create with PAUSE status as dependent pipeline is not done (dataset_pattern=%s,variable=%s)'%(e.dataset_pattern,e.variable))
            status=spconst.PPPRUN_STATUS_PAUSE
    else:
        splog.info('SPEVENTT-018',"Create with PAUSE status as dependent pipeline doesn't exist (dataset_pattern=%s,variable=%s)"%(e.dataset_pattern,e.variable))
        status=spconst.PPPRUN_STATUS_PAUSE

    return status

def events_loop(stop_event):
    while not stop_event.is_set():
        consume_events()
        time.sleep(10)

def start():
    splog.info('SPEVENTT-001',"Event thread starting ...")
    event_thread.start()

def stop():
    splog.info('SPEVENTT-002',"Event thread stopping ...")
    stop_event.set()
    event_thread.join()

# init.

pipelinedep=sppipelinedep.get_module()
stop_event=threading.Event()
event_thread=threading.Thread(name='event_thread', target=events_loop, args=(stop_event,))
