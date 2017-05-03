.. _replication-sdp:

ESGF replication
================

Introduction
************

This document describes how to implement a full ESGF replication pipeline:

.. image:: synda_replication.png
   :scale: 50%
   :alt: Basic replication pipeline
   :align: center

Synda installation
******************

We highly recommend to install Synda modules on a dedicated virtual machine using :ref:`RPM <rpm-install-sdt>` or :ref:`DEB <deb-install-sdt>` packages. This machine will be called *synda-host* in the following.

First, see Synda installation from :ref:`RPM<rpm-install-sdt>` or :ref:`DEB<deb-install-sdt>` package.
Then, install Synda post-processing module from :ref:`RPM<rpm-install-sdp>` or :ref:`DEB<deb-install-sdp>` package.

.. note::

    Synda needs to be installed as ``root`` on *synda-host*. Nevertheless, it can be run with a normal user which is belonging to the ``synda`` Unix group.

.. note::

    The ``synda`` Unix group has to be declared by your system administrator prior to the installation.
    All user ID that are ``synda`` members will be able to run any ``synda [...]`` command.

Synda configuration
*******************

``sdt`` module
--------------

On *synda-host*:

- Set ``post_processing`` parameter to ``true`` in ``sdt.conf``.
- Set ``http_fallback`` parameter to ``true`` in ``sdt.conf``.
- Set ``check_parameter`` parameter to ``0`` in ``sdt.conf`` to allow Synda discovery on another index node than those specified in ``[index]`` section.
- Check the ``host`` parameter is the *synda-host* IP address in ``sdt.conf``.

.. code-block:: text

    [module]
    post_processing=true
    ...
    [download]
    http_fallback=true
    ...
    [behaviour]
    check_parameter=0
    ...
    [post_processing]
    host=xxx.xxx.xxx.xx
    port=18290

- Choose a password to configure RPC server in ``credentials.conf``.
- Set the ESGF ``openid`` and ``password`` in ``credentials.conf``.

.. warning::

    Ensure that your ESGF OpenID is valid and you registered to the appropriate ESGF groups.

.. code-block:: text

    [post_processing]
    username=sdpp
    password=xxxxxx
    ...
    [esgf_credential]
    openid=https://my.data.node/esgf-idp/openid/synda
    password=xxxxxxx

- Add the following constants in ``/usr/share/python/synda/sdt/bin/sdconst.py``:

.. code-block:: python

    EVENT_FILE_COMPLETE='file_complete'
    EVENT_VARIABLE_COMPLETE='variable_complete'
    EVENT_DATASET_COMPLETE='dataset_complete'
    EVENT_DATASET_LATEST='dataset_latest'
    EVENT_LATEST_DATASET_COMPLETE='latest_dataset_complete'

``sdp`` module
--------------

On *synda-host*:

- Set ``eventhread`` parameter to ``1`` in ``sdp.conf``.
- Check the ``host`` parameter is the *synda-host* IP address in ``sdp.conf``.

.. code-block:: text

    [daemon]
    eventthread=1
    host=xxx.xxx.xxx.xx
    ...

- Copy the ``username`` and ``password`` in ``credentials.conf`` for RPC server from ``sdt`` configuration.

.. code-block:: text

    [rpcserver]
    username=sdpp
    password=xxxxxx

- Add the following constants in ``/usr/share/python/synda/sdp/bin/spconst.py``:

.. code-block:: python

    EVENT_FILE_COMPLETE='file_complete'
    EVENT_VARIABLE_COMPLETE='variable_complete'
    EVENT_DATASET_COMPLETE='dataset_complete'
    EVENT_DATASET_LATEST='dataset_latest'
    EVENT_LATEST_DATASET_COMPLETE='latest_dataset_complete'

- Add the project name you want to replicate to the ``AUTHORIZED_PROJECT`` list in ``/usr/share/python/synda/sdp/bin/spconst.py``.

- Depending on its *Data Reference Syntax*, add the project name you want to replicate to the ``PROJECT_WITH_ONE_VARIABLE_PER_DATASET`` list in ``/usr/share/python/synda/sdp/bin/spconst.py``.

``sdw`` module
--------------

This is the client side post-processing module (aka "worker"). This single Python script is fully independent from the Synda stack and can be run remotely or not from *synda-host*. In such a case you will only need to install the following required Python libraries (see also the file header):

 - pip install python-daemon==1.6.1
 - pip install python-jsonrpc==0.8.4
 - pip install simplejson==3.10.0
 - pip install retrying

We will call *worker-host* the remote machine where the worker executes the post-processing scripts.

.. warning::

    *synda-host* and *worker-host* has to be accessible through the network each other without firewall constraints, etc.

.. note::

    The worker is installed with ``synda-pp`` and can be found in ``/usr/bin/synda_wo`` on *synda-host*.

.. warning::

    In the context of the ESGF Replication Working Team, the Synda worker could be run on the ESGF data node (or ESGF Data Transfer Node) used to publish the replicated data.
    A corresponding updated version of the worker is available here: :download:`synda_wo <synda_wo>`.

Target data to replicate
------------------------

Edit one or several selection file focusing the data you want to replicate. See :ref:`the selection file section <selection-file>`.

.. note::

    You can create many selection files (e.g. one per project). Selection file(s) must be stored in the "selection" folder.

Copy those selection files on *synda-host* into the selection folder. This folder is ``/etc/synda/sdt/selection`` by default or can be defined in ``/etc/synda/sdt/sdt.conf`` with the ``selection_path`` parameter. See :ref:`the synda configuration section <config-param-ref-sdt>`

.. warning::

    Use the ``searchapi_host`` selection file parameter to allow Synda to discover files on another index node than those specified in the ``/etc/synda/sdt/sdt.conf``.
    Be careful to disable the facet checking in ``/etc/synda/sdt/sdt.conf`` using ``check_parameter=0``.

.. warning::

    Pay attention to any conflict with the default selection parameters that overwrite the selection file parameters.
    Default parameters are defined into specific templates in the ``default`` folder on *synda-host*.
    This folder is ``/etc/synda/sdt/default`` by default but can be defined in the synda configuration file using the ``default_path`` parameter. See :ref:`the synda configuration section <config-param-ref-sdt>`.

Build a republication pipeline
------------------------------

This republication pipeline is at least composed of 2 tasks to apply on each replicated dataset:

 - The mapfile generation,
 - The ESGF publication as replicas.

Pipeline definition
+++++++++++++++++++

On *synda-host*:

- Edit the file ``/etc/synda/sdp/pipeline/republication.py``. It defines the pipeline and tasks name. This file content must be:

.. code-block:: python

    import sppostprocessingutils

    def get_pipeline():
        return ppp

    # Pipeline name
    name='republication'

    # Transitions/tasks list
    tasks=['mapfile','publication']

    ppp = sppostprocessingutils.build_light_pipeline(name, tasks)


- Edit the file ``/etc/synda/sdp/pipeline/spbindings.py``. It maps each Synda "event" with the corresponding pipeline and the status of the initial task. This file content must be:

.. code-block:: python

    import spconst

    # Mapping: a 'key' event into the corresponding tuple of 'value' pipeline with starting 'status'
    event_pipeline_mapping = {
        spconst.EVENT_VARIABLE_COMPLETE: ('republication', spconst.PPPRUN_STATUS_WAITING)
    }

.. note::

    A Synda "event" is the communication way between ``sdt`` and ``sdp`` to trigger the post-processing entries in ``sdp.db``.
    Each entry corresponds to a dataset life-cycle into the post-processing pipeline.

.. note::

    A pipeline task is also called a Synda "transition".

.. note::

    You can easily manage your pipeline definitions in another folder using the ``pipeline_path`` parameter in ``sdp.conf``. See :ref:`the synda configuration section <config-param-ref-sdp>`.

Scripts
+++++++

A transition name has to be the same as the script you want to apply as post-process.
Due to the RPC server connexion, those scripts can be run outside of *synda-host*. See the worker configuration below. This is very useful for intensive computing process that requires cluster infrastructure.

.. warning::

    Whether your scripts are run remotely or not, all the required dependencies, libraries, compiler, etc. have to be installed on *synda-host* or *worker-host*.

- Edit :download:`mapfile.sh <mapfile.sh>` that will generate mapfiles using the ``esgprep mapfile`` command-line. See `esgf-prepare <http://is-enes-data.github.io/esgf-prepare/>`_.

- Edit and configure :download:`publication.sh <publication.sh>` that will publish the generated mapfiles as replica.

Each script as two main section:

 - The initialization section deserializes the command-line argument submitted by the worker to the script.
 - The main section apply the processing command.

.. warning::

    The provided templates works with some functions to source with :download:`functions.sh <functions.sh>`.

File discovery
**************

Install your selection file on *synda-host*:

.. code-block:: bash

    synda install -s <selection-file>

Or upgrade the file discovery:

.. code-block:: bash

    synda upgrade

At this point, files metadata are stored in local database and data download can begin.

Files download
**************

To start the download, run command below on *synda-host*:

.. code-block:: bash

    service sdt start

At this point, the downloading is in progress and when a dataset is complete a Synda event triggers the corresponding pipeline creation.

Files processing
****************

To start the post-processing, run command below on *synda-host*:

.. code-block:: bash

    service sdp start

At this point, the downloading is in progress and the previous event are consumed by ``sdp`` to create appropriate pipeline entries into the database.
The first transition of each complete dataset has a "waiting" status.

Then, run the worker remotely (i.e., on *worker-host*) or not (i.e., on *synda-host*):

.. code-block:: bash

    synda_wo -H <synda-host-IP> -w <rpc-password> --script_dir /your/scripts

At this point, the worker communicates with the ``sdp.db`` database to pick up information on a dataset pending for a transition to apply.
The worker runs the corresponding script and returns the job result to ``sdp.db``. On success, the transition is set to "done" and moved to the next one.

The worker can be run as a daemon using the ``start``, ``stop`` and ``status`` command:

.. code-block:: bash

    synda_wo start -H <synda-host-IP> -w <rpc-password> --script_dir /your/scripts

.. note::

    In daemon mode, the worker never stops (except in case of error) and regularly checks waiting jobs to process.

The worker is also able to:

- Pick up only one item to process from ``sdp.db``:

.. code-block:: bash

    synda_wo -H <synda-host-IP> -w <rpc-password> --script_dir /your/scripts -1

- Filter the transitions to process:

.. code-block:: bash

    synda_wo -H <synda-host-IP> -w <rpc-password> --script_dir /your/scripts -j transitionA,transitionB

- Filter the pipeline to process:

.. code-block:: bash

    synda_wo -H <synda-host-IP> -w <rpc-password> --script_dir /your/scripts -p pipelineA

By default, the worker log is ``/var/log/sdw/worker.log`` on *synda-host*  and ``/tmp`` on *worker-host*. On *worker-host* you can submit another log directory:

.. code-block:: bash

    synda_wo -H <synda-host-IP> -w <rpc-password> --script_dir /your/scripts -l /your/logs

.. note::

    All those examples can be combined safely.
