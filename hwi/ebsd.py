import pandas as pd
import numpy as np
import os
import copy
import json
from . import app
from flask import request, jsonify, abort, session, send_from_directory, redirect
import datetime

import os

from hydrautils import scenario_utilities as scenarioutils
from hydrautils import attr_utilities as attrutils
from hydrautils import network_utilities as netutils

from werkzeug.exceptions import InternalServerError

from HydraLib.HydraException import HydraError, ResourceNotFoundError
from HydraServer.lib.objects import JSONObject, Dataset

from . import appinterface 


from HydraServer.db import commit_transaction, rollback_transaction
from HydraLib import config

import requests

import logging
log = logging.getLogger(__name__)

global POLYVIS_URL
POLYVIS_URL = app.config.get('POLYVIS_URL', 'http://polyvis.org/')

@app.route('/upload_ebsd_data', methods=['POST'])
def do_upload_ebsd_data():
    """
        Read an excel file containing DO values (amongst others)
        for each WRZ.
        :params:
            scenario_id: int
            data_file: xlsfile
    """

    data = request.get_data()
    user_id = session['user_id']
    
    if data == '' or len(data) == 0:
        log.critical('No data sent')
        return jsonify({"Error" : "No Data Found"}), 400
    
    if len(request.files) > 0:
        data_file = request.files['data_file']
    else:
        return jsonify({"Error" : "No File Specified"}), 400

    scenario_id = int(request.form['scenario_id'])

    scenario = scenarioutils.get_scenario(scenario_id, user_id)

    network_id = scenario.network_id

    _process_data_file(data_file, network_id, scenario_id, user_id)
    upload_dir = app.config['UPLOAD_DIR']

    if not os.path.exists(os.path.join(upload_dir , 'datafiles')):
        os.mkdir(os.path.join(upload_dir , 'datafiles'))
    
    now = datetime.datetime.now().strftime('%Y%m%d%H%M')
    data_file.save(os.path.join(upload_dir , 'datafiles' , now+'_'+data_file.filename))
    
    commit_transaction()

    log.info("File read successfully")

    return jsonify({'status': 'OK', 'message': 'Data saved successfully'})

@app.route('/get_ebsd_results/scenario/<scenario_id>/solution/<solution_id>')
@app.route('/get_ebsd_results')
def do_get_ebsd_results(scenario_id, solution_id):
    """
        Generate an excel file from the results of the ebse model (mga or non-mga).
        Mga / non mga is indicated by use of result ID.

        if no result id is provided to an mga scenario, an exception is thrown
    """
    log.info("Generating excel file...")

    user_id = session['user_id']

    scenario = scenarioutils.get_scenario(scenario_id, user_id)
    log.info("Scenario Retrieved")

    flow_df, cols = _get_flow_data(scenario, solution_id)

    wrz_dfs = _get_balance_data(scenario, solution_id, cols)
    
    folder = os.tempnam()
    os.mkdir(folder)
    outputname = 'EBSD_Results_%s_%s.xlsx'%(scenario.scenario_name, solution_id)
    location = os.path.join(folder, outputname)

    writer = pd.ExcelWriter(location, engine='xlsxwriter')
    flow_df.to_excel(writer, sheet_name='Flows')
    for wrz_name, balance_df in wrz_dfs.items():
        balance_df.to_excel(writer, sheet_name=wrz_name)
    
    workbook = writer.book
    #Formatting...
    #worksheet = writer.sheets['Flows']
    #worksheet = writer.sheets['Balance']

    writer.save()
    
    log.info("File export complete.")
    
    return send_from_directory(folder, outputname, as_attachment=True)

def _get_balance_data(scenario, solution_id, cols):
    n = scenario.network

    #dict of dataframes, keyed on wrz name.
    balance_dict = {}

    ra_dict = {'NODE':{}, 'LINK': {}, 'GROUP':{}, 'NETWORK':{}}
    for rs in scenario.resourcescenarios:
        ra = rs.resourceattr
        resource_id = rs.resourceattr.get_resource_id()
        if ra_dict[ra.ref_key].get(resource_id) is None:
            ra_dict[ra.ref_key][resource_id] = {ra.resource_attr_id:rs}
        else:
            ra_dict[ra.ref_key][resource_id][ra.resource_attr_id] = rs

    #Dict keyed on wrz name, containing sub-dicts describing such things as
    #the in links and out links and attributes 
    wrz_info = {}
    for n in n.nodes:
        if n.types[0].templatetype.type_name == 'demand':
            wrz_data = _get_wrz_data(n, ra_dict, solution_id)
            wrz_df = _make_balance_df(wrz_data, cols)
            balance_dict[n.node_name] = wrz_df

    return balance_dict 

def _get_wrz_data(n, ra_dict, solution_id):

    mga_attrs = ['BALANCE', 'AVAILABLE_DO', 'DI_THR_DATA', 'TOTAL_EXISTING_IMPORT', 'TOTAL_EXISTING_EXPORT']

    in_links = n.links_from
    out_links = n.links_to

    attributes = ra_dict['NODE'].get(n.node_id, {}) 
    rs_dict = {}
    for ra_id in attributes:
        rs = attributes[ra_id]
        attr_name = rs.resourceattr.attr.attr_name
        if attr_name not in mga_attrs:
            continue

        if rs.dataset.get_metadata_as_dict().get('sol_type') is None:
            continue
        val = eval(rs.dataset.value)[solution_id]
        rs_dict[attr_name] = pd.read_json(json.dumps(val)).transpose()


    existing_imports = _get_imports(in_links, ra_dict, solution_id)

    existing_exports = _get_exports(out_links, ra_dict, solution_id)

    selected_options = _get_selected_options(n, ra_dict, solution_id)

    wrz_data = {'in': existing_imports, 'out':existing_exports, 'attributes':rs_dict, 'selected':selected_options}

    return wrz_data


def _make_balance_df(wrz_data, cols):
    """
        wrz data is a dict with
        'in' (a list of link objects),
        'out' (a list of link objects) and
        'attributes'  a dict, keyed on attr_name and valued as a
                      JSON string ready for panda-fication
    """

    attr_idx_map = dict(
          AVAILABLE_DO = ('Initial Supply demand Balance', 'AVAILABLE_DO'),
          BALANCE = ('Final Supply Demand Balance', ''),
          DI_THR_DATA  = ('Initial Supply demand Balance', 'DI_THR_DATA'),
          TOTAL_EXISTING_IMPORT = ('Initial Supply demand Balance', 'TOTAL_EXISTING_IMPORT'),
          TOTAL_EXISTING_EXPORT = ('Initial Supply demand Balance', 'TOTAL_EXISTING_EXPORT'),
    )


    idx_data = [
            ('Initial Supply demand Balance', 'AVAILABLE_DO'),
            ('Initial Supply demand Balance', 'DI_THR_DATA'),
            ('Initial Supply demand Balance', 'TOTAL_EXISTING_IMPORT'),
            ('Initial Supply demand Balance', 'TOTAL_EXISTING_EXPORT'),
          ]
   

    for nodename in wrz_data['in']:
        idx_data.append(('Existing Imports', nodename))

    for nodename in wrz_data['out']:
        idx_data.append(('Existing Exports', nodename))

    for nodename in wrz_data['selected']:
        idx_data.append(('Selected Options', nodename))

    idx_data.append(('Final Supply Demand Balance', ''),)

    balance_cols = pd.MultiIndex.from_tuples(cols)
    
    idx = pd.MultiIndex.from_tuples(idx_data)

    xl_df = pd.DataFrame(index=idx, columns=balance_cols)

    for nodename in wrz_data['in']:
        df = wrz_data['in'][nodename]
        for c in df.columns:
            for i in df.index:
                xl_df[c, i][('Existing Imports', nodename)] = df[c][i]

    for nodename in wrz_data['out']:
        df = wrz_data['out'][nodename]
        for c in df.columns:
            for i in df.index:
                xl_df[c, i][('Existing Exports', nodename)] = df[c][i]

    for nodename in wrz_data['selected']:
        df = wrz_data['selected'][nodename]
        for c in df.columns:
            for i in df.index:
                xl_df[c, i][('Selected Options', nodename)] = df[c][i]

    for attr_name in wrz_data['attributes']:
        df = wrz_data['attributes'][attr_name]
        idx = attr_idx_map[attr_name]
        for  c in df.columns:
            for i in df.index:
                xl_df[(c, i)][idx] = df[c][i]

    return xl_df

def _get_imports(links, ra_dict, solution_id):
    imports = {}
    for l in links:
        attributes = ra_dict['LINK'].get(l.link_id, {})
        for ra_id in attributes:
            rs = attributes[ra_id]
            ra = rs.resourceattr
            if ra.attr.attr_name == 'EXISTING_LINKS':
                if len(rs.dataset.value) == 0:
                    continue
                val = eval(rs.dataset.value)[solution_id]
                link_df = pd.read_json(json.dumps(val)).transpose()
                imports[l.node_b.node_name] = link_df
    
    return imports

def _get_exports(links, ra_dict, solution_id):
    imports = {}
    for l in links:
        attributes = ra_dict['LINK'].get(l.link_id, {})
        for ra_id in attributes:
            rs = attributes[ra_id]
            ra = rs.resourceattr
            if ra.attr.attr_name == 'EXISTING_LINKS':
                if len(rs.dataset.value) == 0:
                    continue
                val = eval(rs.dataset.value)[solution_id]
                link_df = pd.read_json(json.dumps(val)).transpose()
                imports[l.node_a.node_name] = link_df
    
    return imports

def _get_selected_options(wrz, ra_dict, solution_id):
    selected = {}

    inlinks = wrz.links_from
    outlinks = wrz.links_to

    for l in inlinks:
        attributes = ra_dict['LINK'].get(l.link_id, {})
        for ra_id in attributes:
            rs = attributes[ra_id]
            ra = rs.resourceattr
            if ra.attr.attr_name == 'OPTIONAL_LINKS':
                if len(rs.dataset.value) == 0:
                    continue
                val = eval(rs.dataset.value)[solution_id]
                if not val:
                    continue
                link_df = pd.read_json(json.dumps(val)).transpose()
                selected[l.node_a.node_name] = link_df 

    for l in outlinks:
        attributes = ra_dict['LINK'].get(l.link_id, {})
        for ra_id in attributes:
            rs = attributes[ra_id]
            ra = rs.resourceattr
            if ra.attr.attr_name == 'OPTIONAL_LINKS':
                if len(rs.dataset.value) == 0:
                    continue
                val = eval(rs.dataset.value)[solution_id]
                if not val:
                    continue
                link_df = pd.read_json(json.dumps(val)).transpose()
                selected[l.node_b.node_name] = link_df

    return selected

def _get_flow_data(scenario, solution_id):
    log.info('Getting Flow Data')

    flows = {}
    flow_attr_id = None
    jn_attr_id = None
    link_nodes = {}
    link_jns = {}

    #Identify the 'flow' attribute by its name, 'Q'
    for rs in scenario.resourcescenarios:
        ra = rs.resourceattr
        a = ra.attr
        #Only interested in Links
        if ra.link is None:
            continue
        else:
            link_nodes[ra.link.link_name] = (ra.link.node_a.node_name, ra.link.node_b.node_name)
            #Avoid interrogating the attribute each time, if the correct attr ID is known
            if flow_attr_id is not None and ra.attr_id == flow_attr_id:
                flows[ra.link.link_name] = rs.dataset.value
            elif a.attr_name == 'Q':
                flow_attr_id = a.attr_id
                flows[ra.link.link_name] = rs.dataset.value
            elif jn_attr_id is not None and ra.attr_id == jn_attr_id:
                link_jns[ra.link.link_name] = rs.dataset.value
            elif a.attr_name == 'jun_node':
                jn_attr_id = a.attr_id
                link_jns[ra.link.link_name] = rs.dataset.value

    log.info("Flow data extracted")
    flow_dfs = {}
    sample_df = None
    for linkname in flows:

        if flows[linkname] in ('NULL', None, ''):
            continue

        try:
            all_results = json.loads(flows[linkname])
        except:
            log.critical(flows[linkname])
            raise Exception("Flow value on link %s is not valid. Unable to parse JSON."%(linkname))

        result = all_results.get(str(solution_id))
        if result is None:
            raise Exception("Unable to find data for sulution %s on link %s "%(solution_id, linkname))

        #
        flowdf = pd.read_json(json.dumps(result)).transpose()
        
        #If all the values are 0, then there is no flow, hence the option was never chosen
        x = flowdf == 0
        y = x.all()

        if y.all() == False:
            val = pd.read_json(json.dumps(result)).transpose()
            flow_dfs[linkname] = val
            if sample_df is None or (len(val.index) > len(sample_df.index)):
                sample_df = val

    log.info("Flow data converted to dataframes")

    linknames = flow_dfs.keys()

    cols = [
        ('Link', 'From'),
        ('Link', 'Jn'),
        ('Link', 'To'),
    ]

    for c in sample_df.columns:
        for i in sample_df.index:
            cols.append((c, i))

    df_cols = pd.MultiIndex.from_tuples(cols)
    
    xl_df = pd.DataFrame(index=linknames, columns=df_cols)
    
    for linkname in flow_dfs:
        df = flow_dfs[linkname]
        xl_df[('Link', 'From')][linkname] = link_nodes[linkname][0]
        xl_df[('Link', 'Jn')][linkname]   = link_jns[linkname]
        xl_df[('Link', 'To')][linkname]   = link_nodes[linkname][1]

        for c in df.columns:
            for i in df.index:
                xl_df[(c, i)][linkname] = df[c][i]

    return xl_df, cols[3:]


def _process_data_file(data_file, network_id, scenario_id, user_id):
    """
        Process the data file containing WRZ DO data amongst other things 

        returns a dictionary of values, keyed on WRZ name
    """
    log.info('Processing data file %s', data_file.filename)

    xl_df = pd.read_excel(data_file, sheetname=None)

    attr_name_map = {
        'Distribution Input': 'DI',
        'Distribution Input (normal year)': 'DI',
        'Target Headroom' : 'THR',
        #'Potable Water Imported': '' #Not used by original macro
        #'Potable Water Exported': '', # Not used by original macro
        #'Deployable Output (baseline profile without reductions)': '', #Not used by original macro
        'Baseline forecast changes to Deployable Output': 'Change_DO', 
        'Treatment Works Losses': 'PL_RWLOU',
        'Outage allowance': 'PL_RWLOU',
        'Raw Water Losses and Operational Use': 'PL_RWLOU',
        #'Water Available For Use (own sources)': '', #Not used by original macro
        #'Total Water Available For Use': '',
        
    }

    #These are the attributes which we know where they should go wihin Hydra.
    #This should be unnecessary when we have a full map of input files to hydra attributes
    known_attrs = attr_name_map.keys()


    all_attributes = attrutils.get_all_attributes() 

    attr_id_map = {}
    reverse_attr_id_map = {}

    for a in all_attributes:
        if a.attr_name in attr_name_map.values():
            attr_id_map[a.attr_name] = a.attr_id
            reverse_attr_id_map[a.attr_id] = a.attr_name
     
    data_template = None
    wrzs = None
    wrz_nodes = []
    #Key = WRZ name
    #val = dict, keyed on attribute name
    #sub-val = hasahtable value, with scenario columns, time indices.
    attributes = {}
    for scenarioname, scenario_df in xl_df.items():
        log.info("Processing scenario %s", scenarioname)
        if wrzs is None:
            #Get the unique wrz names
            wrzs = set(scenario_df['WRZ'])

            for w in wrzs:
                attributes[w.lower()] = {}
                try:
                    wrz_nodes.append(netutils.get_resource_by_name(network_id, 'NODE', w.lower(), user_id))
                except ResourceNotFoundError, e:
                    log.warn('WRZ %s not found', w)
        
        for rowname in scenario_df.index:
            row = scenario_df.ix[rowname]
            wrzname = row['WRZ'].lower()
            attr_name = row['Component']

            if attr_name not in known_attrs:
                continue
            
            data = row[5:]
            data = data.replace(np.NaN, 0.0)

            if data_template is None:
                data_template = copy.deepcopy(data)
                data_template[:]=0
            
            db_attr_name = attr_name_map[attr_name]
            attr_id = attr_id_map[db_attr_name]

            if attributes[wrzname].get(attr_id):
                #Some attributes are made up of the addition of multiple attributes (PL_RWLOU, for example)
                previousdata = attributes[wrzname][attr_id].get(scenarioname)
                if previousdata is not None:
                    attributes[wrzname][attr_id][scenarioname] = previousdata.add(data)
                else:
                    attributes[wrzname][attr_id][scenarioname] = data
            else:
                attributes[wrzname][attr_id] = {scenarioname : data}

    
    for wrzname in attributes.keys():
        for attr_id in attributes[wrzname].keys():
            for s in xl_df.keys():
                if s not in attributes[wrzname][attr_id].keys(): 
                    attr_name = reverse_attr_id_map[attr_id]
                    #Some attribute / scenario combos are all 0, while others take the values from the DYAA scenario.
                    if attr_name in ('Change_DO', 'PL_RWLOU'):
                        attributes[wrzname][attr_id][s] = attributes[wrzname][attr_id]['DYAA']
                    else:
                        attributes[wrzname][attr_id][s] = data_template
                attributes[wrzname][attr_id][s] = dict(attributes[wrzname][attr_id][s])

    attr_ids = attr_id_map.values()
    new_rs = []
    #Set the values on the actual attributes.
    for n in wrz_nodes:
        for a in n.attributes:
            if a.attr_id in attr_ids:
                
                val = attributes[n.node_name.lower()][a.attr_id]
                ##Insurance policy to ensure the conversion functions are doing
                #the right thing
                vala = scenarioutils._hashtable_to_seasonal(val)
                valb = scenarioutils._seasonal_to_hashtable(vala)
                assert valb == val

                new_rs.append(
                    JSONObject(dict(
                        resource_attr_id = a.resource_attr_id,
                        value =dict(
                            name      = 'EBSD dataset from file %s' % (data_file.filename),
                            type      =  'array',        
                            value     = json.dumps(val),
                            metadata  =  {'type': 'hashtable_seasonal', "sub_key": "SCENARIO", "key": "yr"}
                        )
                    ))
                )

    for r in new_rs:
        r.value = Dataset(r.value)

    newdatasts = scenarioutils.update_resource_data(scenario_id, new_rs, user_id)



@app.route('/run_ebsd_model', methods=['POST'])
def run_ebsd_model():
    """To run an app the following information needs to be transmitted as a json
    string:
    {'id': 'the app id',
     'network_id': number,
     'scenario_id': number,
     'options': {'option1': value1, 'option2': value2, ... }
     }

    'options' is allowed to be empty; entries in the options dict need to
    correspond to a 'name' of a mandatory or non-mandatory argument or a switch
    of an app.
    """
    log.info('Running Model')
    app_id = request.values['app_id']
    network_id = request.values['network_id']
    scenario_name = request.values.get('scenario_name')
    network_name = request.values.get('network_name')
    scenario_id = request.values.getlist('scenario_id')
    default_model_file =  os.path.join(os.path.expanduser('~'), 'EBSD.gms')
    model_file = os.environ.get('EBSD_MODEL', default_model_file)

    for s_id in scenario_id:
        job_id = appinterface.run_app(app_id,
                              network_id,
                              s_id,
                              session['user_id'],
                              scenario_name=scenario_name,
                              network_name=network_name,
                              options={
                                  'gams-model':model_file,
                                  'session_id': session['session_id'],
                                  'server_url': request.url_root,
                              })

    return jsonify(job_id)


@app.route('/export_to_polyvis', methods=['GET', 'POST'])
def do_export_to_polyvis():
    """
        Pass a multi-soluton scenario (produced by MGA for example) into polyvis,
        Finds all results of type 'MGA', from the same attribute and condenses them
        into a single value (taking 'DYAA' aas the default scenario if they'yre nested hashtables')
        re-formatting it into a csv structure.
        Return a URL generated by polyvis and redirect to that URL
    """
    log.info('Exoorting to polyvis...')
    if len(request.args) > 0:
        scenario_id = int(request.args['scenario_id'])
    else:
        args = json.loads(request.get_data())
        scenario_id = args['scenario_id']
    user_id = session['user_id']

    log.info("Setting up lookup dicts")
    all_attributes = attrutils.get_all_attributes() 

    attr_id_map = {}
    reverse_attr_id_map = {}

    for a in all_attributes:
        attr_id_map[a.attr_name] = a.attr_id
        reverse_attr_id_map[a.attr_id] = a.attr_name

    scenario = scenarioutils.get_scenario(scenario_id, user_id)

    ra_dict = {'NODE':{}, 'LINK': {}, 'GROUP':{}, 'NETWORK':{}}
    rs_map = {}
    for rs in scenario.resourcescenarios:
        ra = rs.resourceattr
        resource_id = rs.resourceattr.get_resource_id()
        if ra_dict[ra.ref_key].get(resource_id) is None:
            ra_dict[ra.ref_key][resource_id] = {ra.resource_attr_id:rs}
        else:
            ra_dict[ra.ref_key][resource_id][ra.resource_attr_id] = rs
        
        rs_map[rs.resource_attr_id] = rs

    #Get the cost attribute on the network to identify all the solutions:
    network = scenario.network
    for ra in network.attributes:
        if reverse_attr_id_map[ra.attr_id].lower() == 'cost':
            costval = rs_map[ra.resource_attr_id].dataset.value


    if costval is None:
        raise Exception("Could not find a 'cost' value on the network.")
    
    soln_dict = {}
    #Found the cost value, now parse it and pick out all the solution IDS.
    try:
        costval = eval(costval)
        solution_ids = costval.keys()
        for k, v in costval.items():
            #int-ify the solution id for nicer sorting.
            try:
                k = int(k)
            except:
                pass
            soln_dict[k] = {'cost':v}
    except Exception, e:
        log.exception(e)
        raise Exception("The value %s does not apper to contain valid solution ids. "
                        "Please ensure it is a json serialisable hashtable,"
                        " where the keys are solution IDS and the values are costs."%costval)
    
    json_vals = {'cost': costval}

    calculated_metric_names = [
        'BALANCE',
        'AVAILABLE_DO',
        'DI_THR_DATA',
        'TOTAL_EXISTING_IMPORT',
        'TOTAL_EXISTING_EXPORT',
    ]

    calculated_metric_ids = []
    for cm in calculated_metric_names:
        calculated_metric_ids.append(attr_id_map[cm])

    all_metrics = calculated_metric_ids
     
    log.info('Exporting scenario %s to polyvis', scenario_id)

    #A dict, keyed on node ID, containing its 'selected' status for each solution.
    #We'll parse and move the approproate things around afterwards
    selected_dict = {}
    for n in network.nodes:
        if n.types[0].templatetype.type_name == 'demand':
            selected_options = _get_selected_nodes(n, ra_dict)
            selected_dict.update(selected_options)  
    
    #Dict keyed on wrz name, containing sub-dicts describing such things as
    #the in links and out links and attributes 
    log.info("Setting up metric lookup dictionaries for nodes & links")
    all_attr_values = {}
    for n in network.nodes:

        for ra in n.attributes:
            if ra.attr_id in all_metrics:

                attr_name = reverse_attr_id_map[ra.attr_id]
                rs = rs_map.get(ra.resource_attr_id)
                if rs is None:
                    log.warn('No value found for %s on node %s', attr_name, n.node_name)
                    continue
                
                value = rs.dataset
                if all_attr_values.get(attr_name):
                    all_attr_values[attr_name].append(value)
                else:
                    all_attr_values[attr_name] = [value]

    for l in network.links:
        for ra in l.attributes:
            if ra.attr_id in all_metrics:

                attr_name = reverse_attr_id_map[ra.attr_id]
                rs = rs_map.get(ra.resource_attr_id)
                if rs is None:
                    log.warn('No value found for %s on node %s', attr_name, l.link_name)
                    continue
                value = rs.dataset
                if all_attr_values.get(attr_name):
                    all_attr_values[attr_name].append(value)
                else:
                    all_attr_values[attr_name] = [value]
    
    #transpose the data so it's now keyed on solution ID.
    #Each solution's value should either be a scalar (ex: cost) or a hashtable
    #We generate a single number by summing the average of the 'DYAA' columns
    #for each attribute, if it's a hashtable.
    target_col = 'DYAA'
    
    log.info('Populating the solution dictionary with the metric attributes')
    for attr_name, values in all_attr_values.items():
        for dataset in values:
            try:
                json_val = json.loads(dataset.value)
                for soln_id, solnval in json_val.items():
                    soln_df = pd.read_json(json.dumps(solnval)).transpose()
                    if target_col not in soln_df.columns:
                        continue

                    attrsum = soln_df[target_col].sum()

                    #Try to int-ify the solution identifier as it'll provide a more nicely sorted csv file.
                    try:
                        soln_id = int(soln_id)
                    except:
                        pass

                    if soln_dict[soln_id].get(attr_name):
                        soln_dict[soln_id][attr_name] = soln_dict[soln_id][attr_name] + attrsum
                    else:
                        soln_dict[soln_id][attr_name] = attrsum
                
            except Exception, e:
                log.exception(e)
                log.warn('%s: %s', attr_name, dataset.value[:100])
                return e

    log.info('Populating the solution dictionary with the selected options')
    for selectednode, values in selected_dict.items():
        values = eval(values)
        for solution_id, value in values.items():
            try:
                solution_id = int(solution_id)
            except:
                pass

            if not value or len(value) == 0:
                soln_dict[solution_id][selectednode] = 0
            else:
                soln_dict[solution_id][selectednode] = 1

    log.info("Converting solution data to a dataframe.") 
    soln_df = pd.read_json(json.dumps(soln_dict)).transpose()

    csv_text = soln_df.to_csv()

    log.info("Saving file.") 
    f = open('/tmp/df.txt', 'w+')
    f.writelines('ID' + csv_text)
    f.flush()

    f = open('/tmp/df.txt', 'r')

    client = requests.session()

    # Retrieve the CSRF token first
    client.get(POLYVIS_URL)  # sets cookie
    csrftoken = client.cookies['csrftoken']

    resp = client.post(POLYVIS_URL+'upload_parallel_data',
                       files={'csv':f},
                       data={'csrfmiddlewaretoken':csrftoken},
                       headers=dict(Referer=POLYVIS_URL))
    log.info("Polyvis URL generated. Returning %s", resp.url) 
    return resp.url


def _get_selected_nodes(wrz, ra_dict):
    selected = {}

    inlinks = wrz.links_from
    outlinks = wrz.links_to

    for l in inlinks:
        attributes = ra_dict['LINK'].get(l.link_id, {})
        for ra_id in attributes:
            rs = attributes[ra_id]
            ra = rs.resourceattr
            if ra.attr.attr_name == 'AL':
                if len(rs.dataset.value) == 0:
                    continue
                val = rs.dataset.value
                if not val or val == 'NULL':
                    continue
                selected[l.node_a.node_name] = val 

    for l in outlinks:
        attributes = ra_dict['LINK'].get(l.link_id, {})
        for ra_id in attributes:
            rs = attributes[ra_id]
            ra = rs.resourceattr
            if ra.attr.attr_name == 'AL':
                if len(rs.dataset.value) == 0:
                    continue
                val = rs.dataset.value
                if not val or val == 'NULL':
                    continue
                selected[l.node_b.node_name] = val 

    return selected
