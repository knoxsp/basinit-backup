from flask import  request, session, redirect, url_for, escape, send_file, jsonify, Markup
import json

from HydraServer.util.hdb import login_user

from HydraLib.HydraException import HydraError, PermissionError, ResourceNotFoundError

from HydraLib.hydra_dateutil import ordinal_to_timestamp

from flask import render_template

from werkzeug import secure_filename
import zipfile
import os
import sys
import datetime
import urllib2

from hydrautils.run_hydra_app import *

basefolder = os.path.dirname(__file__)

from HydraServer.lib.objects import JSONObject, ResourceScenario

from hydrautils.app_utilities import delete_files_from_folder, create_zip_file, get_apps_properties

import hydrautils.project_utilities as projutils
import hydrautils.network_utilities as netutils
import hydrautils.attr_utilities as attrutils
import hydrautils.template_utilities as tmplutils
import hydrautils.dataset_utilities as datasetutils
import hydrautils.scenario_utilities as scenarioutils
import hydrautils.user_utilities as userutils

from hydrautils.export_network import export_network_to_pywr_json, export_network_to_excel, export_network_to_csv

from hydrautils.import_network import import_network_from_csv_files, import_network_from_excel, import_network_from_pywr_json

from . import app, appinterface, requires_login

from HydraServer.db import commit_transaction, rollback_transaction, DBSession


# 'server/'
@app.route('/')
def index():
    app.logger.info("Index")
    session_info = request.environ.get('beaker.session')
    app.logger.info("Session: %s", session_info)
    if 'user_id' not in session_info:
        app.logger.info("Going to login page.")
        return render_template('login.html', msg="")
    else:
        #Manually expire all db sessions?
        DBSession.remove()
        user_id = session_info['user_id']
        username = escape(session_info['username'])
        projects = projutils.get_projects(user_id)
        app.logger.info("Logged in. Going to projects page.")
        return render_template('projects.html',
                               display_name=username,
                               username=username,
                               projects=projects)

# 'server/login'
@app.route('/login', methods=['GET', 'POST'])
def do_login():
    app.logger.info("Received login request.")
    if request.method == 'POST':
        try:
            user_id = login_user(request.form['username'], request.form['password'])
        except Exception, e:
            app.logger.exception(e)
            app.logger.warn("Bad login for user %s", request.form['username'])
            return render_template('login.html',  msg="Unable to log in")

        request.environ['beaker.session']['username'] = request.form['username']
        request.environ['beaker.session']['user_id'] = user_id
        request.environ['beaker.session'].save()
        
        session['username'] = request.form['username']
        session['user_id'] = user_id
        session['session_id'] = request.environ['beaker.session'].id

        app.logger.info("Good login %s. Redirecting to index (%s)"%(request.form['username'], url_for('index')))

        app.logger.info(session)

        return redirect(url_for('index'))

    app.logger.warn("Login request was not a post. Redirecting to login page.")
    return render_template('login.html',
                           msg="")

@app.route('/do_logout', methods=['GET', 'POST'])
@requires_login
def do_logout():
    app.logger.info("Logging out %s", request.environ['beaker.session']['username'])
    # remove the username from the session if it's there
    request.environ['beaker.session'].delete()
    session.pop('username', None)
    session.pop('user_id', None)
    session.pop('session_id', None)
    app.logger.info(request.environ.get('beaker.session'))
    return redirect(url_for('index', _external=True))

# set the secret key.  keep this really secret:
app.secret_key = '\xa2\x98\xd5\x1f\xcd\x97(\xa4K\xbfF\x99R\xa2\xb4\xf4M\x13R\xd1]]\xec\xae'


@app.route('/about', methods=['GET'])
@requires_login
def go_about():
    return render_template('about.html')

@app.route('/templates', methods=['GET'])
@requires_login
def go_templates():
    user_id = request.environ['beaker.session']['user_id']
    all_templates = tmplutils.get_all_templates(user_id)
    return render_template('templates.html', templates=all_templates)

@app.route('/get_templates', methods=['GET'])
@requires_login
def do_get_all_templates():
    user_id = request.environ['beaker.session']['user_id']
    all_templates = tmplutils.get_all_templates(user_id)
    return all_templates

@app.route('/newtemplate', methods=['GET'])
@requires_login
def go_new_template():
    all_attributes = attrutils.get_all_attributes()
    return render_template('template.html',
                                new=True,
                              all_attrs=all_attributes,
                          )

@app.route('/template/<template_id>', methods=['GET'])
@requires_login
def go_template(template_id):

    user_id = request.environ['beaker.session']['user_id']
    all_attributes = attrutils.get_all_attributes()
    tmpl = tmplutils.get_template(template_id, user_id)

    typeattr_lookup = {}

    for rt in tmpl.templatetypes:
        if rt.typeattrs is not None:
            typeattr_lookup[rt.type_id] = [ta.attr_id for ta in rt.typeattrs]
        else:
            typeattr_lookup[rt.type_id] = []

    attr_id_name_lookup = dict([(a.attr_id, a.attr_name) for a in all_attributes])
    attr_dimen_lookup = dict([(a.attr_id, a.attr_dimen) for a in all_attributes])

    app.logger.info(tmpl)
    return render_template('template.html',
                           new=False,
                           all_attrs=all_attributes,
                           attr_id_name_lookup=attr_id_name_lookup,
                           template=tmpl,
                           attr_dimen_lookup=attr_dimen_lookup,
                            typeattr_lookup=typeattr_lookup)


@app.route('/create_attr', methods=['POST'])
@requires_login
def do_create_attr():

    user_id = request.environ['beaker.session']['user_id']

    d = json.loads(request.get_data())

    attr_j = JSONObject(d)

    newattr = attrutils.create_attr(attr_j, user_id)

    commit_transaction()

    return newattr.as_json()

@app.route('/create_dataset', methods=['POST'])
@requires_login
def do_create_dataset():

    user_id = request.environ['beaker.session']['user_id']

    d = json.loads(request.get_data())

    dataset_j = JSONObject(d)

    newdataset = datasetutils.create_dataset(dataset_j, user_id)

    commit_transaction()

    app.logger.info(newdataset)
    return newdataset.as_json()

@app.route('/create_template', methods=['POST'])
@requires_login
def do_create_template():

    user_id = request.environ['beaker.session']['user_id']

    d = json.loads(request.get_data())

    template_j = JSONObject(d)

    newtemplate = tmplutils.create_template(template_j, user_id)

    commit_transaction()

    return newtemplate.as_json()


@app.route('/load_template', methods=['POST'])
@requires_login
def do_load_template():

    now = datetime.datetime.now().strftime("%y%m%d%H%M")

    basefolder = os.path.join(os.path.dirname(os.path.realpath(__file__)), TEMPLATE_FOLDER, now)
    if not os.path.exists(basefolder):
        os.mkdir(basefolder)

    user_id = request.environ['beaker.session']['user_id']

    template_file = request.files['import_file']

    template_file.save(os.path.join(basefolder, template_file.filename))

    f = open(os.path.join(basefolder, template_file.filename))
    f_arr = f.readlines()
    text = ''.join(f_arr)

    newtemplate = tmplutils.load_template(text, user_id)

    commit_transaction()

    return newtemplate.as_json()

@app.route('/update_template', methods=['POST'])
@requires_login
def do_update_template():

    user_id = request.environ['beaker.session']['user_id']

    d = json.loads(request.get_data())

    template_j = JSONObject(d)

    newtemplate = tmplutils.update_template(template_j, user_id)

    commit_transaction()

    return newtemplate.as_json()

@app.route('/delete_template', methods=['POST'])
@requires_login
def do_delete_template(template_id):

    user_id = request.environ['beaker.session']['user_id']

    status = delete_template(template_id, user_id)

    commit_transaction()

    return status

@app.route('/apply_template_to_network', methods=['POST'])
@requires_login
def do_apply_template_to_network(template_id, network_id):

    user_id = request.environ['beaker.session']['user_id']

    apply_template_to_network(template_id, network_id, user_id)

    commit_transaction()

    return redirect(url_for('go_network', network_id=network_id))

@app.route('/project/<project_id>', methods=['GET'])
@requires_login
def go_project(project_id):
    """
        Get a user's projects
    """
    user_id = request.environ['beaker.session']['user_id']
    project = projutils.get_project(project_id, user_id)
    app.logger.info("Project %s retrieved", project.project_name)
    '''
    if the project has only one network and the network has only one scenario, it will display network directly
    '''
    network_types = tmplutils.get_all_network_types(user_id)
    return render_template('project.html',\
                              username=session['username'],\
                              display_name=session['username'],\
                              project=project,
                               all_network_types=network_types
                               )

@app.route('/create_network', methods=['POST'])
@requires_login
def do_create_network():

    user_id = request.environ['beaker.session']['user_id']

    d = json.loads(request.get_data())

    d['scenarios'] = [{"name": "Baseline", "resourcescenarios":[]}]

    net_j = JSONObject(d)

    net = netutils.create_network(net_j, user_id)

    commit_transaction()

    return net.as_json()

@app.route('/delete_network', methods=['POST'])
@requires_login
def do_delete_network():

    user_id = request.environ['beaker.session']['user_id']

    d = json.loads(request.get_data())

    netutils.delete_network(d['network_id'], user_id)

    commit_transaction()

    return json.dumps({'status': 'OK'})

@app.route('/create_project', methods=['POST'])
@requires_login
def do_create_project():

    user_id = request.environ['beaker.session']['user_id']

    d = json.loads(request.get_data())

    proj_j = JSONObject(d)

    proj = projutils.create_project(proj_j, user_id)

    commit_transaction()

    return proj.as_json()

@app.route('/delete_project', methods=['POST'])
@requires_login
def do_delete_project():

    user_id = request.environ['beaker.session']['user_id']

    d = json.loads(request.get_data())

    projutils.delete_project(d['project_id'], user_id)

    commit_transaction()

    return json.dumps({'status': 'OK'})

@app.route('/share_project', methods=['POST'])
@requires_login
def do_share_project():

    user_id = request.environ['beaker.session']['user_id']
    d = json.loads(request.get_data())
    app.logger.info('Project sharing details: %s'%d)

    read_only = 'Y'
    if d.get('allow-edit') is not None:
        read_only = 'N'

    share = 'N'
    if d.get('allow-resharing') is not None:
        share = 'Y'

    projutils.share_project(
                    d['project_id'],
                    d['usernames'],
                    read_only,
                    share, user_id)

    commit_transaction()

    return json.dumps({'status': 'OK'})

@app.route('/share_network', methods=['POST'])
@requires_login
def do_share_network():

    user_id = request.environ['beaker.session']['user_id']
    d = json.loads(request.get_data())
    app.logger.info('network sharing details: %s'%d)

    read_only = 'Y'
    if d.get('allow-edit') is not None:
        read_only = 'N'

    share = 'N'
    if d.get('allow-resharing') is not None:
        share = 'Y'

    netutils.share_network(
                    d['network_id'],
                    d['usernames'],
                    read_only,
                    share, user_id)

    commit_transaction()

    return json.dumps({'status': 'OK'})

def allowed_file (filename):
    ext=os.path.splitext(filename)[1][1:].lower()
    if ext in ALLOWED_EXTENSIONS:
        return True
    else:
        return False

@app.route('/add_network_note/<network_id>/<note_text>', methods=['GET'])
@requires_login
def do_add_network_note(network_id, note_text):
    pass

@app.route('/network/<network_id>', methods=['GET'])
@requires_login
def go_network(network_id):
    """
        Get a network
    """

    user_id = request.environ['beaker.session']['user_id']

    node_coords, links, node_name_map, extents, network, nodes_, links_ = netutils.get_network(network_id, user_id)

    attr_id_name_map = netutils.get_attr_id_name_map()

    if network.types is not None and len(network.types) > 0:
        template_id = network.types[0].templatetype.template_id

        tmpl = tmplutils.get_template(template_id, user_id)
        #Build a map from type id to layout, to make it easy for the javascript
        #and html templates to access type layouts
        type_layout_map = {}
        for tmpltype in tmpl.templatetypes:
            layout = tmpltype.layout
            if layout == None:
                layout = {}
            type_layout_map[tmpltype.type_id] = layout
    else:
        tmpl = JSONObject({'templatetypes': []});
        type_layout_map = {}

    layout = {}
    if network.layout is not None:
        try:
            layout = json.loads(network.layout)
        except:
            log.info("Network has no layout")
            layout = {}

    if network.projection:
        try:
            proj = network.projection.split(":")[1]
            system = network.projection.split(":")[0].lower()
            resp = urllib2.urlopen("http://spatialreference.org/ref/%s/%s/proj4js/"%(system,proj))
            network.projection_crs = resp.read().split(" = ")[1]
        except:
            log.critical("Error with projection")
            network.projection = None
            network.projection_crs = ""

    if len(network.scenarios) == 0:
        default_scenario = {'name': 'Baseline', 'network_id': network.network_id}
        s = scenarioutils.add_scenario(JSONObject(default_scenario), user_id)
        scenario = s
        network.scenarios.append(s)
        commit_transaction()
    else:
        scenario = network.scenarios[0]

    scenario_summaries = {}
    for s in network.scenarios:
        test = ordinal_to_timestamp(s.start_time)
        scenobj = dict( 
            start_time = str(ordinal_to_timestamp(s.start_time)) if s.start_time else '',
            end_time   = str(ordinal_to_timestamp(s.end_time)) if s.end_time else '',
            time_step  = s.time_step if s.time_step else '',
            locked     = s.locked,
            status     = s.status,
            description = s.scenario_description,
            name        = s.scenario_name,
        )
        scenario_summaries[s.scenario_id] = scenobj

    rgi_lookup = {}
    for rgi in scenario.resourcegroupitems:
        key = 'group-' + str(rgi.group_id)
        if rgi_lookup.get(key) is None:
            rgi_lookup[key] = {'NODE':[], 'LINK':[], 'GROUP':[]}

            rgi_lookup[key][rgi.ref_key].append(JSONObject(rgi))
        else:
            rgi_lookup[key][rgi.ref_key].append(JSONObject(rgi))

    available_apps_by_category = {}
    available_apps_by_id = {}
    for a in appinterface.installed_apps_as_dict():
        category = a['category']
        if available_apps_by_category.get(category):
            available_apps_by_category[category].append(a)
        else:
            available_apps_by_category[category] = [a]
        available_apps_by_id[a['id']] = a

    app.logger.info(available_apps_by_category)

    return render_template('network.html',\
                scenario_id=scenario.scenario_id,
                node_coords=node_coords,\
                links=links,\
                resourcegroupitems = JSONObject(rgi_lookup),\
                username=session['username'],\
                display_name=session['username'],\
                node_name_map=node_name_map,\
                extents=extents,\
                network=network,\
                network_layout = json.dumps(layout),\
                nodes_=nodes_,\
                links_=links_, \
                scenarios=json.dumps(scenario_summaries),\
                attr_id_name=attr_id_name_map,\
                template = tmpl,\
                type_layout_map=type_layout_map,\
                apps = JSONObject(available_apps_by_category),\
                app_dict = JSONObject(available_apps_by_id))


@app.route('/delete_resource', methods=['POST'])
@requires_login
def do_delete_resource():

    user_id = request.environ['beaker.session']['user_id']

    d = json.loads(request.get_data())

    resource_to_delete = JSONObject(d)

    app.logger.info("Deleting resource %s (%s).",resource_to_delete.id, resource_to_delete.resource_id)

    netutils.delete_resource(resource_to_delete.id,resource_to_delete.resource_type, user_id)

    commit_transaction()

    app.logger.info("Resource %s (%s) deleted.",resource_to_delete.id, resource_to_delete.resource_id)

    return 'OK'

@app.route('/add_node', methods=['POST'])
@requires_login
def do_add_node():

    user_id = request.environ['beaker.session']['user_id']

    d = json.loads(request.get_data())

    node_j = JSONObject(d)

    newnode = netutils.add_node(node_j, user_id)

    commit_transaction()

    app.logger.info("Node %s added. New ID of %s",newnode.node_name, newnode.node_id)

    return newnode.as_json()


@app.route('/update_node', methods=['POST'])
@requires_login
def do_update_node():

    user_id = request.environ['beaker.session']['user_id']

    d = json.loads(request.get_data())

    node_j = JSONObject(d)

    updatednode = netutils.update_node(node_j, user_id)

    commit_transaction()

    app.logger.info("Node %s updated.",updatednode.node_name)

    return updatednode.as_json()

@app.route('/delete_node', methods=['POST'])
@requires_login
def do_delete_node():

    user_id = request.environ['beaker.session']['user_id']

    d = json.loads(request.get_data())

    node_id = d['node_id']

    netutils.delete_node(node_id, user_id)

    commit_transaction()

    app.logger.info("node %s deleted.",node_id)

    return 'OK'

@app.route('/add_link', methods=['POST'])
@requires_login
def do_add_link():

    user_id = request.environ['beaker.session']['user_id']

    d = json.loads(request.get_data())

    link_j = JSONObject(d)

    newlink = netutils.add_link(link_j, user_id)

    commit_transaction()

    app.logger.info("Link %s added. New ID of %s",newlink.link_name, newlink.link_id)

    return newlink.as_json()

@app.route('/delete_link', methods=['POST'])
@requires_login
def do_delete_link():

    user_id = request.environ['beaker.session']['user_id']

    d = json.loads(request.get_data())

    link_id = d['link_id']

    netutils.delete_link(link_id, user_id)

    commit_transaction()

    app.logger.info("link %s deleted.",link_id)

    return 'OK'

@app.route('/add_group', methods=['POST'])
@requires_login
def do_add_group():

    user_id = request.environ['beaker.session']['user_id']

    d = json.loads(request.get_data())

    group  = d['group']
    items  = d['items']
    scenario_id = d['scenario_id']
    group_j = JSONObject(group)

    newgroup = netutils.add_group(group_j, user_id)

    group_id = newgroup.group_id
    #Done this way as the server function can add items to multiple groups if the groups
    #are specifed on the items themselves.
    json_items = []
    for i in items:
        j = JSONObject(i)
        j['group_id'] = group_id
        json_items.append(j)

    newitems = scenarioutils.add_resource_group_items(scenario_id, json_items, user_id)

    commit_transaction()

    newgroup.items = newitems

    app.logger.info("Group %s added. New ID of %s",newgroup.group_name, newgroup.group_id)

    return newgroup.as_json()


@app.route('/upgate_group', methods=['POST'])
@requires_login
def do_update_group():

    user_id = request.environ['beaker.session']['user_id']

    d = json.loads(request.get_data())

    group  = d['group']
    items  = d['items']
    scenario_id = d['scenario_id']
    group_j = JSONObject(group)

    updatedgroup = netutils.update_group(group_j, user_id)

    s = scenarioutils.get_scenario(scenario_id, user_id)

    old_group_items = []
    new_group_items = []
    existing_group_items = []
    incoming_items = []
    item_lookup = {}
    new_item_lookup = {}
    for rgi in s.resourcegroupitems:
        if rgi.group_id == int(group['id']):
            existing_group_items.append((rgi.ref_key, rgi.get_resource_id()))
            item_lookup[(rgi.ref_key, rgi.get_resource_id())] = rgi

    for i in items:
        i['group_id'] = group['id']
        incoming_items.append((i['ref_key'], int(i['ref_id'])))
        new_item_lookup[(i['ref_key'], int(i['ref_id']))] = i

    existing_group_items = set(existing_group_items)
    incoming_items = set(incoming_items)

    items_to_delete = existing_group_items.difference(incoming_items)
    items_to_add    = incoming_items.difference(existing_group_items)
    items_to_keep    = incoming_items.intersection(existing_group_items)

    items_to_keep = [JSONObject(item_lookup[k]) for k in items_to_keep]
    item_ids_to_delete = [item_lookup[k].item_id for k in items_to_delete]
    json_items_to_add = [JSONObject(new_item_lookup[k]) for k in items_to_add]

    newitems = scenarioutils.add_resource_group_items(scenario_id, json_items_to_add, user_id)
    scenarioutils.delete_resource_group_items(scenario_id, item_ids_to_delete, user_id)

    commit_transaction()

    updatedgroup.items = items_to_keep + newitems

    app.logger.info("Group %s updated.",updatedgroup.group_name)

    return updatedgroup.as_json()

@app.route('/get_resource_data', methods=['POST'])
@requires_login
def do_get_resource_data():

    user_id = request.environ['beaker.session']['user_id']

    pars= json.loads(request.get_data())
    network_id = pars['network_id']
    scenario_id = int(pars['scenario_id'])
    resource_id= pars['res_id']
    resource_type=pars['resource_type']

    ##This flag indicates that just the RSs should be returned as json rather
    ##than the rendered attributes html
    raw = pars.get('raw', 'N')

    app.logger.info("Getting resource attributes for: %s", str(pars))
    resource, resource_scenarios=scenarioutils.get_resource_data(network_id,
                                                  scenario_id,
                                                  resource_type,
                                                  resource_id,
                                                  user_id)

    attr_id_name_map = netutils.get_attr_id_name_map()

    if raw.lower() == 'y':
        json_resp = json.dumps({'resourcescenarios':resource_scenarios, 'attr_id_name_map': attr_id_name_map})
        return json_resp
    else:
        return render_template('attributes.html',
                           attr_id_name_map=attr_id_name_map,
                           resource_scenarios=resource_scenarios.values(),
                           resource=resource,
                            resource_id=resource_id,
                            scenario_id=scenario_id,
                            resource_type=resource_type,)


@app.route('/update_resourcedata', methods=['POST'])
@requires_login
def do_update_resource_data():

    user_id = request.environ['beaker.session']['user_id']

    d = json.loads(request.get_data())

    app.logger.info(d)

    if len(d) == 0:
        return 'OK'

    rs_list = [ResourceScenario(rs) for rs in d['rs_list']]

    app.logger.info(rs_list)

    scenarioutils.update_resource_data(d['scenario_id'], rs_list, user_id)

    commit_transaction()

    return 'OK'

def get_model_file (network_id, model_file):
    model_file_ = 'network_' + network_id + '.gms'
    model_folder=os.path.join(basefolder, 'data', 'Models')
    directory=os.path.join(model_folder, network_id)
    #make folder
    if not os.path.exists(model_folder):
        os.makedirs(model_folder)
    if not os.path.exists(directory):
        os.makedirs(directory)
    server_model_name=os.path.join(directory, model_file_)
    print "server_model_name", server_model_name
    if model_file!= None:
        if(os.path. exists(server_model_name)):
            os.remove(server_model_name)
        os.rename(model_file, server_model_name)
    if os.path.isfile(server_model_name) ==True:
        return server_model_name
    else:
        return None

def get_pp_exe(app_):
    if app_.lower()=='gams':
        app= get_apps_properties("GAMSAuto")
        if app != None:
            if app['command'].lower().strip()=='exe':
                return os.path.join(app['location'], app['main'])
            else:
                return app['command']+" "+os.path.join(app['location'], app['main'])
    elif app_.lower() == 'pywr':
        return os.path.join(basefolder, 'Apps', 'Pywr_App', 'PywrAuto',  'PywrAuto.py')


def get_app_args (network_id, scenario_id, model_file):
    return {'t': network_id, 's': scenario_id, 'm': model_file}


def run_gams_app(network_id, scenario_id, model_file=None):
    exe=get_pp_exe('gams')
    print exe
    model_file =get_model_file(network_id, model_file)
    #model_file=get_model(network_id, model_file)
    print model_file
    if(model_file ==None):
        return jsonify({}), 202, {'Error': 'Model file is not available, please upload one'}
    args = get_app_args (network_id, scenario_id, model_file)
    pid=run_app(exe, args, False)
    return jsonify({}), 202, {'Address': url_for('appstatus',
                                                  task_id=pid)}


def run_pywr_app(network_id, scenario_id):

    exe=get_pp_exe('pywr')
    os.chdir(os.path.dirname(exe))

    exe="python " + exe
    args = {'t': network_id, 's': scenario_id}
    app.logger.info("Running Pywr App at %s with args %s", exe, args)
    pid=run_app(exe, args, False)
    return jsonify({}), 202, {'Address': url_for('appstatus',
                                                  task_id=pid)}


@app.route('/status/<task_id>')
@requires_login
def appstatus(task_id):
    task, progress , total, status=get_app_progress(task_id)
    if task == True:
        response = {
            'current': progress,
            'total': total,
            'status': status
        }
    else:
        response = {
            'current': 100,
            'total': 100,
            'status':status
        }
    return jsonify(response)

@app.route('/import_uploader', methods=['POST'])
@requires_login
def import_uploader():
    uploaded_file=None
    upload_dir = app.config['UPLOAD_DIR']
    basefolder = os.path.join(os.path.dirname(os.path.realpath(__file__)), upload_dir)
    extractedfolder = os.path.join(basefolder, 'temp')
    if not os.path.exists(extractedfolder):
        os.makedirs(extractedfolder)
    else:
        delete_files_from_folder(extractedfolder)
    type= request.files.keys()[0]
    app_name=request.form['app_name']
    print type, app_name

    if(app_name.strip().startswith('ex')):#') =='ex_pywr'):
        print "It is from expor"
        network_id = request.form['network_id']
        scenario_id = request.form['scenario_id']
        if (int(network_id) == 0 or int(scenario_id) == 0):
            return "Error, no network and scenario are specified ..."
        else:
            return import_app(network_id, scenario_id, app_name)

    print "Work till here...", app_name

    file = request.files[type]
    if app_name != 'run_gams_model' and app_name != 'run_pywr_app' :
        if (file.filename == '' ) :
            return jsonify({}), 202, {'Error': 'No file is selected'}
        elif not allowed_file(file.filename) :
            return jsonify({}), 202, {'Error': 'zip file is only allowed'}
    if (file.filename != ''):
        filename = secure_filename(file.filename)
        uploaded_file = os.path.join(basefolder, filename)
        file.save(uploaded_file)

    if (app_name == 'run_gams_model'):
        network_id = request.form['network_id']
        scenario_id = request.form['scenario_id']
        return run_gams_app(network_id, scenario_id, uploaded_file)

    elif(app_name == 'run_pywr_app'):
        network_id = request.form['network_id']
        scenario_id = request.form['scenario_id']
        return run_pywr_app(network_id, scenario_id)


    print "1. app_name: "+app_name

    zip = zipfile.ZipFile(uploaded_file)
    print "2. app_name: "+app_name

    zip.extractall(extractedfolder)
    print "3. app_name: "+app_name


    project_id = request.form['project_id']

    print "app_name: "+app_name
    if(app_name== 'csv'):
        pid = import_network_from_csv_files(project_id, extractedfolder, basefolder)
    elif (app_name== 'pywr'):
        pid=import_network_from_pywr_json(project_id, extractedfolder, basefolder)
    elif (app_name== 'import_excel'):
        pid=import_network_from_excel( project_id, extractedfolder, basefolder)
    else:
        pid=type+ ' is not recognized.'

    app.logger.info("PID: ", pid)
    try:
        int (pid)
        return jsonify({}), 202, {'Address': url_for('appstatus',
                                                   task_id=pid)}
    except:
        return jsonify({}), 202, {'Error': pid}


def import_app(network_id, scenario_id, app_name):

    upload_dir = app.config['UPLOAD_DIR']
    basefolder = os.path.join(os.path.dirname(os.path.realpath(__file__)), upload_dir)
    directory = os.path.join(basefolder, 'temp')
    app.logger.info("ex_pywr: ", basefolder)
    delete_files_from_folder(directory)
    result=None
    zip_file_name = os.path.join(directory, ('network_' + network_id + '.zip'))
    if (app_name == 'ex_pywr'):
        result = export_network_to_pywr_json(directory, network_id, scenario_id, basefolder)
    elif (app_name == 'ex_excel'):
        result = export_network_to_excel(directory, network_id, scenario_id, basefolder)
    elif (app_name == 'ex_csv'):
        result = export_network_to_csv(directory, network_id, scenario_id, basefolder)
    else:
        return "application not recognized : "+app_name
    try:
        int(result)
        app.logger.info("URL: ", url_for('appstatus',task_id=result))
        app.logger.info( "result ", result)
        return jsonify({}), 202, {'Address': url_for('appstatus',
                                                     task_id=result), 'directory':directory}
    except:
        print "Error ..."
        return "Error: "+result

@app.route('/send_zip_files',  methods=['GET', 'POST'])
@requires_login
def send_zip_files():
        app.logger.info("======>> Send method called ....", request.form)

        pars = json.loads(Markup(request.args.get('pars')).unescape())

        network_id = pars['network_id']
        scenario_id = pars['scenario_id']
        directory = pars['directory']

        return redirect(url_for('go_export_network', network_id=network_id,
                            scenario_id=scenario_id, directory=directory))


@app.route('/header/ <network_id>, <scenario_id>, <directory>' , methods=['POST','GET'])
@requires_login
def go_export_network(network_id, scenario_id, directory):
    zip_file_name = os.path.join(directory, ('network_' + network_id + '.zip'))
    create_zip_file(directory, zip_file_name)
    app.logger.info('Zip file name: %s', zip_file_name)
    app.logger.info('Directory: %s', directory)

    if not os.path.exists(zip_file_name):
        return "An error occurred!!!"

    return send_file(zip_file_name, as_attachment=True)

@app.route("/clone_scenario", methods=['POST'])
@requires_login
def do_clone_scenario():
    pars= json.loads(request.get_data())
    scenario_id   = pars['scenario_id']
    app.logger.info("Cloning scenario %s", scenario_id)
    scenario_name = pars['scenario_name']
    user_id       = request.environ['beaker.session']['user_id']

    new_scenario = scenarioutils.clone_scenario(scenario_id, scenario_name, user_id)

    commit_transaction()

    return new_scenario.as_json()

@app.route("/get_usernames_like", methods=['POST'])
@requires_login
def get_usernames_like():
    pars = request.form.to_dict()

    user_id = request.environ['beaker.session']['user_id']

    usernames = userutils.get_usernames_like(pars['q'], user_id)

    return_data = [{'text':u, 'id':u} for u in usernames]

    return json.dumps(return_data)

@app.route("/get_resource_scenario", methods=['POST'])
@requires_login
def do_get_resource_scenario():
    pars= json.loads(request.get_data())
    scenario_id   = pars['scenario_id']
    resource_attr_id = pars['resource_attr_id']
    log.info("Fetching resource scenario %s %s",resource_attr_id, scenario_id)
    user_id       = request.environ['beaker.session']['user_id']
   
    rs = scenarioutils.get_resource_scenario(resource_attr_id, scenario_id, user_id)

    return rs.as_json()

@app.route("/get_resource_scenarios", methods=['POST'])
@requires_login
def do_get_resource_scenarios():
    pars= json.loads(request.get_data())
    scenario_ids   = pars['scenario_ids']
    resource_attr_id = int(pars['resource_attr_id'])
    log.info("Fetching multiple resource scenarios %s %s",resource_attr_id, scenario_ids)
    user_id       = request.environ['beaker.session']['user_id']
    
    return_rs = {}
    for scenario_id in scenario_ids:
        try:
            rs = scenarioutils.get_resource_scenario(resource_attr_id, int(scenario_id), user_id)
            return_rs[scenario_id] = rs
        except ResourceNotFoundError, e:
            log.warn("resource scenario for %s not found in scenario %s"%(resource_attr_id, scenario_id))

    app.logger.info('%s resource scenarios retrieved', len(return_rs))

    return json.dumps(return_rs)
