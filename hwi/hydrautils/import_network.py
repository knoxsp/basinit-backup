import os
from run_hydra_app import *

def get_json_file(directory):
    files_list=os.listdir(directory)
    for filename in files_list:
        print "File Name: ==========>", filename
        ext=os.path.splitext(filename)[1][1:].strip().lower()
        print "ext: ", ext
        if ext== 'json':
            return filename
    return None

def import_network_from_pywr_json(project_id, directory, basefolder):
    os.chdir(directory)
    json_file = get_json_file(directory)
    print "JSON File: ", json_file
    if json_file == None:
        return ["pywr json file is not found ..."]

    #if not os.path.exists('pywr.json'):
    #    return ["pywr json file (pywr.json) is not found ..."]
    pp = basefolder.split(os.path.sep)
    pp1 = pp[0: (len(pp) - 1)]
    basefolder = os.path.sep.join(pp1)
    pywr_import=os.path.join(basefolder,"Apps","pywr_app", "Importer","PywrImporter.py")
    exe="python " + pywr_import
    args={"f": json_file}
    return run_app(exe, args, False)


def import_network_from_excel(project_id, directory, basefolder):
    os.chdir(directory)
    excel_file=None
    for file in os.listdir(directory):
        if file.endswith(".xls") or file.endswith(".xlsx"):
            excel_file=file
            break
    if excel_file == None:
        return ["Excel file is not found ..."]
    pp = basefolder.split(os.path.sep)
    pp1 = pp[0: (len(pp)    - 1)]
    basefolder = os.path.sep.join(pp1)
    excel_import = os.path.join(basefolder, "Apps", "ExcelApp", "ExcelImporter", "ExcelImporter.exe")
    exe=excel_import
    args={"i": directory+os.path.sep+ excel_file ,"m": directory+os.path.sep+"template.xml", "p": project_id}
    return run_app(exe, args, False)


def import_network_from_csv_files(project_id, directory, basefolder):
    print "Running for csv files ..."
    os.chdir(directory)
    if not  os.path.exists('network.csv'):
        return "Network file (network.csv) is not found ...."
    pp = basefolder.replace(os.path.sep.join(["HydraServer","python","HydraServer","ui"]), "").split(os.path.sep)
    pp1 = pp[0: (len(pp) - 1)]
    basefolder = os.path.sep.join(pp1)
    csv_import = os.path.join(basefolder, "HydraPlugins", "CSVplugin", "ImportCSV", "ImportCSV.py")
    use_wd=False
    exe="python " + csv_import

    if os.path.exists('network.csv'):
        args = {'t': 'network.csv', 'm': 'template.xml', "p": project_id, 'x': ''}
    else:
        args={'t': 'network.csv', 'x':''}
    return run_app(exe, args, use_wd)
