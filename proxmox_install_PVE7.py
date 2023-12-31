#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#
# (c) Rene Hadler, Mario Loderer, iteas IT Services GmbH
# support@iteas.at
# www.iteas.at
#

import sys
import time
import socket
import subprocess
import requests
import json

# Globale Variablen
VERSION = "1.2.6"
TITLE = "iteas Proxmox Installer " + VERSION
CHECK_INTERNET_IP = "77.235.68.35"
VM_TEMPLATE_CIFS_SHARE = "//10.255.18.3/proxmox-install"
VM_TEMPLATE_CIFS_USER = "localbackup02"
SMB_ADMIN_PASSWD = "backmode123"


try:
    CONSOLE_ROWS, CONSOLE_COLS = subprocess.check_output(['stty', 'size']).split()
except:
    CONSOLE_ROWS = 40
    CONSOLE_COLS = 100

GUI_WIN_WIDTH = 100 if int(CONSOLE_COLS) > 110 else (int(CONSOLE_COLS) - 10)

class Logger:
    def __init__(self):
        self.f = fr = open("proxmox_install.log", "w+")

    def log(self, text):
        self.f.write(text)

    def close(self):
        self.f.close()

logger = Logger()

# Befehle ausführen
def run_cmd(command, argShell=False):
    try:
        return subprocess.call(command.split(" ") if argShell == False else command, shell=argShell)
    except:
        e = sys.exc_info()[0]
        retval = gui_yesno_box("Fehler", "Befehl <%s> war nicht erfolgreich, Fehlermeldung: %s -- Installation abbrechen?" % (command, e))
        if retval[0] == 0:
            exit(1)

def apt_install(pkgs, argShell=False, force=False):
    command = "apt-get install -y %s %s" % (pkgs, "--force-yes" if force else "")
    try:
        print(command)
        ret = subprocess.call(command.split(" ") if argShell == False else command, shell=argShell)
        if ret != 0:
            retval = gui_yesno_box("APT-Fehler", 'Befehl <%s> war nicht erfolgreich, Rueckgabewert war nicht 0, Fehlermeldung: \n--\n%s \n--\nInstallation abbrechen?' % (command, ret[2]))
            if retval[0] == 0:
                exit(1)
    except SystemExit:
        exit(1)
    except:
        e = sys.exc_info()[0]
        retval = gui_yesno_box("Fehler", "Befehl <%s> war nicht erfolgreich, Fehlermeldung: %s -- Installation abbrechen?" % (command, e))
        if retval[0] == 0:
            exit(1)

def run_cmd_output(command, argShell=False):
    p = subprocess.Popen(command.split(" "), stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=argShell)
    ret = p.wait()
    return (ret, p.stdout.read().decode('UTF-8'), p.stderr.read().decode('UTF-8'))

def run_cmd_stdout(command, argShell=False):
    p = subprocess.Popen(command, stdout=subprocess.PIPE, shell=argShell)
    ret = p.wait()
    return (ret, p.stdout.read().decode('UTF-8'))

def run_cmd_stderr(command, argShell=False):
    p = subprocess.Popen(command, stderr=subprocess.PIPE, shell=argShell)
    ret = p.wait()
    return (ret, p.stderr.read().decode('UTF-8'))

def run_cmd_stdin(command, argShell=False):
    p = subprocess.Popen(command, stdin=subprocess.PIPE, shell=argShell)
    return p

# Oberflächen / GUI
def gui_message_box(title, text):
    return run_cmd_stderr(["whiptail", "--backtitle", TITLE, "--msgbox", text, "--title", title, "20", str(GUI_WIN_WIDTH)])

def gui_text_box(file):
    return run_cmd_stderr(["whiptail", "--backtitle", TITLE, "--textbox", file, "20", str(GUI_WIN_WIDTH)])

def gui_input_box(title, text, default=""):
    return run_cmd_stderr(["whiptail", "--backtitle", TITLE, "--inputbox", text, "20", str(GUI_WIN_WIDTH), default, "--title", title])

def gui_yesno_box(title, text):
    return run_cmd_stderr(["whiptail", "--backtitle", TITLE, "--yesno", text, "--title", title, "20", str(GUI_WIN_WIDTH)])

def gui_password_box(title, text):
    return run_cmd_stderr(["whiptail", "--backtitle", TITLE, "--passwordbox", text.encode('UTF-8'), "8", str(GUI_WIN_WIDTH), "--title", title.encode('UTF-8')])

def gui_menu_box(title, text, menu):
    return run_cmd_stderr(["whiptail", "--backtitle", TITLE, "--menu", text, "--title", title, "28", str(GUI_WIN_WIDTH), "22"] + menu)

def gui_checklist_box(title, text, checklist):
    ret = run_cmd_stderr(["whiptail", "--backtitle", TITLE, "--checklist", text, "--title", title, "24", str(GUI_WIN_WIDTH), "14"] + checklist)
    return (ret[0], [] if ret[1] == "" else [x.replace('"', "") for x in ret[1].split(" ")])

def gui_radiolist_box(title, text, radiolist):
    return run_cmd_stderr(["whiptail", "--backtitle", TITLE, "--radiolist", text, "--title", title, "24", str(GUI_WIN_WIDTH), "14"] + radiolist)

class gui_progress_box():
    def __init__(self, text, progress):
        self.p = run_cmd_stdin(["whiptail", "--backtitle", TITLE, "--gauge", text, "6", "50", str(progress)])

    def update(self, prog):
        upd = "%s\n" % prog
        self.p.stdin.write(upd.encode('utf-8'))
        self.p.stdin.flush()

    def finish(self):
        self.p.stdin.close()

def gui_password_verify_box(title, text, text2):
    password = ""
    while password == "":
        retval = gui_password_box(title, text)
        if retval[1] == "":
            continue

        retval2 = gui_password_box(title, text2)
        if retval2[1] == "":
            continue

        if retval[1] == retval2[1]:
            password = retval[1]
        else:
            gui_message_box(title, "Fehler bei der Passworteingabe, die Passwoerter stimmen nicht ueberein!")

    return password

# Sonstige Funktionen
def check_internet():
    try:
        s = socket.create_connection((CHECK_INTERNET_IP, 80), 5)
        return True
    except:
        return False

def check_filesystem():
    try:
        zfsc = run_cmd_output('zfs list')
        if zfsc[0] == 1 or zfsc[2].find('no datasets') != -1:
            return 'standard'
        else:
            return 'zfs'
    except:
        return 'standard'

def check_systemip(show_prefix = True):
    zfsc = run_cmd_stdout("ip addr show vmbr0 | grep 'inet' | grep -v 'inet6' | cut -d' ' -f6", argShell=True)
    if show_prefix == True:
        return zfsc[1].strip()
    else:
        return zfsc[1].strip().split("/")[0]

def check_systemipnet():
    try:
        zfsc = check_systemip()
        if zfsc == '':
            return ''
        else:
            # Nicht immer true
            ipf = zfsc.split(".")
            return "%s.%s.%s.0/%s" % (ipf[0], ipf[1], ipf[2], ipf[3].split("/")[1])
    except:
        return ''

def file_replace_line(file, findstr, replstr, encoding='utf-8'):
    try:
        fp = open(file, "r+", encoding=encoding)
        buf = ""
        for line in fp.readlines():
            if line.find(findstr) != -1:
                line = replstr + "\n"

            buf += line

        fp.close()
        fr = open(file, "w+", encoding=encoding)
        fr.write(buf)
        fr.close()
    except FileNotFoundError:
        e = sys.exc_info()[0]
        retval = gui_yesno_box("Fehler", "Datei <%s> wurde nicht gefunden, Fehlermeldung: %s -- Installation abbrechen?" % (file, e))
        if retval[0] == 0:
            exit(1)

def file_create(file, str):
    fr = open(file, "w+")
    fr.write(str + "\n")
    fr.close()

def file_append(file, str):
    fr = open(file, "a")
    fr.write(str + "\n")
    fr.close()

# Installer Start
class Installer():
    def __init__(self):
        self.internet = False
        self.fqdn = socket.getfqdn()
        try:
            self.domain = self.fqdn.split(".")[1] + "." + self.fqdn.split(".")[2]
            self.hostname = socket.gethostname()
        except:
            gui_message_box("Installer", "FQDN ist nicht richtig gesetzt, Installation wird abgebrochen!")
            exit(1)

        self.machine_vendor = "other"
        self.machine_type = "virt"
        self.environment = "stable"
        self.monitoring = "checkmk"
        self.license = ""
        self.filesystem = ""
        self.vm_import = []
        self.lxc_import = []
        self.storage_import = ""
        self.share_clients = []
        self.proxy = False
        self.desktop = "kein"
        self.puppet = "kein"

        self.ipmi_config = False
        self.ipmi_ip = ""
        self.ipmi_netmask = ""
        self.ipmi_gateway = ""
        self.ipmi_dns = ""
        self.ipmi_user = ""
        self.ipmi_pass = ""

        # Installer Variablen
        self.MACHINE_VENDORS = {"hp": "HP < Gen 10", "hp10": "HP Gen 10", "tk": "Thomas Krenn", "other": "Andere"}
        self.MACHINE_TYPES = {"virt": "Virtualisierung", "backup": "Backup"}
        self.ENVIRONMENTS = {"stable": "Stabile Proxmox Enterprise Updates", "test": "Proxmox Testing Updates", "noupdate": "Keine Proxmox Updates"}
        self.MONITORINGS = {"none": "Keine", "checkmk": "CheckMK Agent"}
        self.FILESYSTEMS = {"standard": "Standard (ext3/4, reiserfs, xfs)", "zfs": "ZFS"}
        self.DESKTOPS = {
            "kein": "Nein",
            "plasma": "KDE5-Plasma",
            "plasma-light": "KDE5-Plasma Light",
            "plasma-light-win": "KDE5-Plasma Light Windows Workstation",
            "i3": "i3-WM (testing)"
        }
        self.VM_IMPORTS = {
            "220": {"name": "Windows 11 Pro", "template": True},
            "225": {"name": "Windows 10 Pro", "template": True},
            "169": {"name": "Windows Server 2022 Englisch", "template": True},
            "148": {"name": "Windows Server 2019 Englisch", "template": True},
            "222": {"name": "Windows Server 2019 Deutsch", "template": True},
            "127": {"name": "Rocky9 Standard", "template": True},
            "170": {"name": "Ubuntu Server Standard 22.04", "template": True}
            
        }
        self.LXC_IMPORTS = {
            "143": {"name": "ITEAS CT Template Ubuntu 22.04 priv", "template": True },
            "168": {"name": "ITEAS CT Template Ubuntu 22.04 unpriv", "template": True },
            "145": {"name": "Iteas Backupsolution Enterprise", "template": False },
            "123": {"name": "APP-Web-Template", "template": True },
            "102": {"name": "Samba Backupassist mit ADS Anbindung", "template": True },
            "121": {"name": "Samba Backupassist ohne ADS Anbindung", "template": True },
        }
        self.PUPPETS = {
            "kein": "Nein",
            "generic": "Generische Installation",
            "proxmox-desktop": "Proxmox Desktop"
        }

    def start(self):
        gui_message_box("Installer", "Willkommen beim iteas Proxmox Installer!")
        self.internet = check_internet()
        self.filesystem = check_filesystem()
        if check_systemipnet() != '':
            self.share_clients.append(check_systemipnet())
        self.step1()

    def step1(self):
        step1_val = gui_menu_box("Schritt 1", "Kontrollieren bzw. konfigurieren Sie die entsprechenden Werte und gehen Sie dann auf 'Weiter'.",
                                    ["Internet", "JA" if self.internet == True else "NEIN",
                                     "Hostname", self.hostname,
                                     "Domain", self.domain,
                                     "Dateisystem", self.FILESYSTEMS[self.filesystem],
                                     " ", " ",
                                     "Maschinenhersteller", self.MACHINE_VENDORS[self.machine_vendor],
                                     "Maschinentyp", self.MACHINE_TYPES[self.machine_type],
                                     "IPMI-Konfiguration", "Ja" if self.ipmi_config == True else "Nein",
                                     "Proxmox-Umgebung", self.ENVIRONMENTS[self.environment],
                                     "Proxmox-Lizenz", "Keine" if self.license == "" else self.license,
                                     "VM-Template-Import", ",".join([self.VM_IMPORTS[x]["name"] for x in self.vm_import]) if len(self.vm_import) > 0 else "Keine",
                                     "LXC-Template-Import", ",".join([self.LXC_IMPORTS[x]["name"] for x in self.lxc_import]) if len(self.lxc_import) > 0 else "Keine",
                                     "Import-Storage", "Keine" if self.storage_import == "" else self.storage_import,
                                     "Freigabe-Clients-SMB", ",".join([x for x in self.share_clients]) if len(self.share_clients) > 0 else "Alle",
                                     "apt-Proxy", "Nein" if self.proxy == False else "Ja",
                                     "Desktop", self.DESKTOPS[self.desktop],
                                     "Monitoring-Agent", self.MONITORINGS[self.monitoring],
                                     "Puppet", self.PUPPETS[self.puppet],
                                     " ", " ",
                                     "Weiter", "Installation fortsetzen"])

        # Abbrechen
        if step1_val[0] == 1 or step1_val[0] == 255:
            exit(0)

        # Eintrag wurde gewählt
        if step1_val[1] == "Maschinenhersteller":
            self.step1_machine_vendor()

        elif step1_val[1] == "Maschinentyp":
            self.step1_machine_type()

        elif step1_val[1] == "Proxmox-Umgebung":
            self.step1_environment()

        elif step1_val[1] == "Monitoring-Agent":
            self.step1_monitoring()

        elif step1_val[1] == "Proxmox-Lizenz":
            self.step1_license()

        elif step1_val[1] == "apt-Proxy":
            self.step1_aptproxy()

        elif step1_val[1] == "Desktop":
            self.step1_desktop()

        elif step1_val[1] == "VM-Template-Import":
            self.step1_vmtemplateimport()

        elif step1_val[1] == "LXC-Template-Import":
            self.step1_lxctemplateimport()

        elif step1_val[1] == "Internet":
            check_internet()
            self.step1()

        elif step1_val[1] == "Freigabe-Clients-SMB":
            self.step1_shareclients()

        elif step1_val[1] == "Weiter":
            self.step2()

        elif step1_val[1] == "Puppet":
            self.step1_puppet()

        elif step1_val[1] == "IPMI-Konfiguration":
            self.step1_ipmi_main()

        elif step1_val[1] == "Import-Storage":
            self.step1_import_storage()

        else:
            self.step1()

    def step1_ipmi_main(self):
        step1_val = gui_menu_box("IPMI-Konfiguration", "Kontrollieren bzw. konfigurieren Sie IPMI 'Weiter'.",
                                 ["IPMI-Konfiguration ", "Ja" if self.ipmi_config == True else "Nein",
                                  " ", " ",
                                  "IP-Adresse", self.ipmi_ip,
                                  "IP-Subnet", self.ipmi_netmask,
                                  "Gateway", self.ipmi_gateway,
                                  "DNS", self.ipmi_dns,
                                  " ", " ",
                                  "Benutzername", self.ipmi_user,
                                  "Passwort", self.ipmi_pass[0:3] + (len(self.ipmi_pass)-3)*"*",
                                  " ", " ",
                                  "Zurueck", "Hauptmenu"])

        # Abbrechen
        if step1_val[0] == 1 or step1_val[0] == 255:
            self.step1()

        # Eintrag wurde gewählt
        if step1_val[1] == "IPMI-Konfiguration ":
            self.step1_ipmi_config()

        elif step1_val[1] == "IP-Adresse":
            self.step1_ipmi_ip()

        elif step1_val[1] == "IP-Subnet":
            self.step1_ipmi_netmask()

        elif step1_val[1] == "Gateway":
            self.step1_ipmi_gateway()

        elif step1_val[1] == "DNS":
            self.step1_ipmi_dns()

        elif step1_val[1] == "Benutzername":
            self.step1_ipmi_user()

        elif step1_val[1] == "Passwort":
            self.step1_ipmi_pass()

        elif step1_val[1] == "Zurueck":
            self.step1()

        else:
            self.step1_ipmi_main()

    def step1_ipmi_config(self):
        retval = gui_yesno_box("IPMI", "Mochten Sie IPMI konfigurieren?")
        if retval[0] == 0:
            self.ipmi_config = True
        elif retval[0] == 1:
            self.ipmi_config = False

        # Abbrechen
        if retval[0] == 255:
            self.step1_ipmi_main()
            return

        self.step1_ipmi_main()

    def step1_ipmi_ip(self):
        retval = gui_input_box("IPMI IP-Adresse", "IP-Adresse eingeben", self.ipmi_ip)
        # Abbrechen
        if retval[0] == 1 or retval[0] == 255:
            self.step1_ipmi_main()
            return

        self.ipmi_ip = retval[1]
        self.step1_ipmi_main()

    def step1_ipmi_netmask(self):
        retval = gui_input_box("IPMI IP-Subnet", "IP-Subnet eingeben", self.ipmi_netmask)
        # Abbrechen
        if retval[0] == 1 or retval[0] == 255:
            self.step1_ipmi_main()
            return

        self.ipmi_netmask = retval[1]
        self.step1_ipmi_main()

    def step1_ipmi_gateway(self):
        retval = gui_input_box("IPMI Gateway", "Gateway eingeben", self.ipmi_gateway)
        # Abbrechen
        if retval[0] == 1 or retval[0] == 255:
            self.step1_ipmi_main()
            return

        self.ipmi_gateway = retval[1]
        self.step1_ipmi_main()

    def step1_ipmi_dns(self):
        retval = gui_input_box("IPMI DNS", "DNS eingeben", self.ipmi_dns)
        # Abbrechen
        if retval[0] == 1 or retval[0] == 255:
            self.step1_ipmi_main()
            return

        self.ipmi_dns = retval[1]
        self.step1_ipmi_main()

    def step1_ipmi_user(self):
        retval = gui_input_box("IPMI Benutzer", "Benutzer eingeben", self.ipmi_user)
        # Abbrechen
        if retval[0] == 1 or retval[0] == 255:
            self.step1_ipmi_main()
            return

        self.ipmi_user = retval[1]
        self.step1_ipmi_main()

    def step1_ipmi_pass(self):
        retval = gui_password_box("IPMI Passwort", "Passwort eingeben")
        # Abbrechen
        if retval[0] == 1 or retval[0] == 255:
            self.step1_ipmi_main()
            return

        self.ipmi_pass = retval[1]
        self.step1_ipmi_main()

    def step1_machine_vendor(self):
        list = []
        for key, val in self.MACHINE_VENDORS.items():
            list += [key, val, "ON" if self.machine_vendor == key else "OFF"]

        retval = gui_radiolist_box("Schritt 1: Maschinenhersteller", "Waehlen sie den passenden Maschinenhersteller", list)
        # Abbrechen
        if retval[0] == 1 or retval[0] == 255:
            self.step1()
            return

        self.machine_vendor = retval[1]
        self.step1()

    def step1_machine_type(self):
        list = []
        for key, val in self.MACHINE_TYPES.items():
            list += [key, val, "ON" if self.machine_type == key else "OFF"]

        retval = gui_radiolist_box("Schritt 1: Maschinentyp", "Waehlen sie den passenden Maschinentyp", list)
        # Abbrechen
        if retval[0] == 1 or retval[0] == 255:
            self.step1()
            return

        self.machine_type = retval[1]
        self.step1()

    def step1_environment(self):
        list = []
        for key, val in self.ENVIRONMENTS.items():
            list += [key, val, "ON" if self.environment == key else "OFF"]

        retval = gui_radiolist_box("Schritt 1: Proxmox-Umgebung", "Waehlen sie die Proxmox-Umgebung", list)
        # Abbrechen
        if retval[0] == 1 or retval[0] == 255:
            self.step1()
            return

        self.environment = retval[1]
        self.step1()

    def step1_monitoring(self):
        list = []
        for key, val in self.MONITORINGS.items():
            list += [key, val, "ON" if self.monitoring == key else "OFF"]

        retval = gui_radiolist_box("Schritt 1: Monitoring-Agent", "Waehlen sie den Monitoring-Agenten", list)
        # Abbrechen
        if retval[0] == 1 or retval[0] == 255:
            self.step1()
            return

        self.monitoring = retval[1]
        self.step1()

    def step1_license(self):
        retval = gui_input_box("Schritt 1: Proxmox-Lizenz", "Geben Sie den Proxmox-Schluessel ein", self.license)
        # Abbrechen
        if retval[0] == 1 or retval[0] == 255:
            self.step1()
            return

        self.license = retval[1]
        self.step1()

    def step1_aptproxy(self):
        retval = gui_yesno_box("Installer", "Mochten Sie den iteas apt-Proxy benutzen?")
        if retval[0] == 0:
            self.proxy = True
        elif retval[0] == 1:
            self.proxy = False

        # Abbrechen
        if retval[0] == 255:
            self.step1()
            return

        self.step1()

    def step1_desktop(self):
        list = []
        for key, val in self.DESKTOPS.items():
            list += [key, val, "ON" if self.desktop == key else "OFF"]

        retval = gui_radiolist_box("Schritt 1: Proxmox-Desktop", "Waehlen sie einen Desktop", list)
        # Abbrechen
        if retval[0] == 1 or retval[0] == 255:
            self.step1()
            return

        self.desktop = retval[1]
        self.step1()

    def step1_vmtemplateimport(self):
        list = []
        for key, val in self.VM_IMPORTS.items():
            list += [key, val["name"], "ON" if key in self.vm_import else "OFF"]

        retval = gui_checklist_box("Schritt 1: VM-Template-Import", "Waehlen sie die VMs die importiert werden sollen", list)
        # Abbrechen
        if retval[0] == 1 or retval[0] == 255:
            self.step1()
            return

        self.vm_import = []
        for val in retval[1]:
            self.vm_import += [val]

        self.step1()

    def step1_lxctemplateimport(self):
        list = []
        for key, val in self.LXC_IMPORTS.items():
            list += [key, val["name"], "ON" if key in self.lxc_import else "OFF"]

        retval = gui_checklist_box("Schritt 1: LXC-Template-Import", "Waehlen sie die LXC Container die importiert werden sollen", list)
        # Abbrechen
        if retval[0] == 1 or retval[0] == 255:
            self.step1()
            return

        self.lxc_import = []
        for val in retval[1]:
            self.lxc_import += [val]

        self.step1()

    def step1_shareclients(self):
        retval = gui_input_box("Schritt 1: Freigabe-Clients", "Geben Sie die Clients/Netze an, die Zugriffe auf die Freigaben am Proxmox Host haben sollen. Mehrere Eintraege muessen durch Leerzeichen getrennt sein.", " ".join(self.share_clients))
        # Abbrechen
        if retval[0] == 1 or retval[0] == 255:
            self.step1()
            return

        self.share_clients = retval[1].split(" ")
        self.step1()

    def step1_puppet(self):
        list = []
        for key, val in self.PUPPETS.items():
            list += [key, val, "ON" if self.puppet == key else "OFF"]

        retval = gui_radiolist_box("Schritt 1: Puppet", "Waehlen sie eine Puppet Installationsart", list)
        # Abbrechen
        if retval[0] == 1 or retval[0] == 255:
            self.step1()
            return

        self.puppet = retval[1]
        self.step1()

    def step1_import_storage(self):
        list = []
        jstorages = json.loads(run_cmd_stdout("pvesh get /storage --output-format json", argShell=True)[1])
        for storage in jstorages:
            list += [storage["storage"], storage["content"], "ON" if self.storage_import == storage["storage"] else "OFF"]

        retval = gui_radiolist_box("Schritt 1: Import-Storage", "Waehlen sie ein Storage für den Template Import", list)
        # Abbrechen
        if retval[0] == 1 or retval[0] == 255:
            self.step1()
            return

        self.storage_import = retval[1]
        self.step1()

    def step2(self):

        if self.environment == "stable" and self.license == "":
            gui_message_box("Installer", "Sie muessen eine Lizenz angeben wenn Enterprise Updates ausgewaehlt wurden!")
            self.step1()
            return

        if self.internet == False:
            gui_message_box("Installer", "Es muss eine Internetverbindung bestehen um fortzufahren!")
            self.step1()
            return

        if (len(self.vm_import) > 0 or len(self.lxc_import) > 0) and self.storage_import == "":
            gui_message_box("Installer", "Sie müssen ein Import-Storage angeben!")
            self.step1()
            return

        # Set locales
        file_replace_line("/etc/locale.gen", "# de_AT.UTF-8 UTF-8", "de_AT.UTF-8 UTF-8")
        file_replace_line("/etc/locale.gen", "# de_DE.UTF-8 UTF-8", "de_DE.UTF-8 UTF-8")
        run_cmd('locale-gen', argShell=True)

        ############ Allgemeine Konfiguration
        if self.license != "":
            retval = run_cmd_output('pvesubscription set ' + self.license)
            if retval[0] == 255:
                gui_message_box("Proxmox Lizenzinstallation", "Die Lizenz konnte nicht installiert werden, bitte pruefen Sie Ihre Lizenznummer. Fehler: " + retval[2])
                self.step1()
                return

            time.sleep(30)

            # Warte maximal für 5 Minuten für Registrierung
            maxwait = 300
            curwait = 0
            lictest = run_cmd_stdout('pvesubscription get', argShell=True)
            while lictest[1].find('status: Active') == -1 and curwait < maxwait:
                print("Warte auf Registrierung der Proxmox-Subscription..." + str(curwait))
                time.sleep(10)
                lictest = run_cmd_stdout('pvesubscription get', argShell=True)
                curwait += 10

            # Warte maximal für 5 Minuten für Enterprise-Repo Zugriff
            curwait = 0
            httpuser = run_cmd_stdout("pvesubscription get | grep 'key:.*' | cut -f2 -d:", argShell=True)[1].strip()
            httppass = run_cmd_stdout("pvesubscription get | grep 'serverid:.*' | cut -f2 -d:", argShell=True)[1].strip()

            repotest = requests.get('https://enterprise.proxmox.com/debian/pve', auth=(httpuser, httppass))
            while repotest.status_code != requests.codes.ok and curwait < maxwait:
                print("Warte auf Freischaltung des Enterprise-Repos..." + str(curwait))
                time.sleep(10)
                repotest = requests.get('https://enterprise.proxmox.com/debian/pve', auth=(httpuser, httppass))
                curwait += 10

        # Proxmox Testing Quellen aktivieren
        if self.environment == "test":
            file_create("/etc/apt/sources.list.d/pve-enterprise.list", "# deb https://enterprise.proxmox.com/debian/pve bullseye pve-enterprise")
            file_create("/etc/apt/sources.list.d/pve-no-subscription.list", "deb http://download.proxmox.com/debian/pve bullseye pve-no-subscription")
        elif self.environment == "noupdate":
            file_create("/etc/apt/sources.list.d/pve-enterprise.list", "# deb https://enterprise.proxmox.com/debian/pve bullseye pve-enterprise")
            file_create("/etc/apt/sources.list.d/pve-no-subscription.list", "# deb http://download.proxmox.com/debian/pve bullseye pve-no-subscription")

        # If lvm-thin convert to standard file storage if backup-machine
        if self.machine_type == "backup" and run_cmd('pvesh get /storage | grep -i local-lvm', argShell=True) == 0:
            run_cmd('pvesh delete /storage/local-lvm')
            run_cmd('lvremove /dev/pve/data -f')
            run_cmd('lvcreate -Wy -l100%FREE -ndata pve')
            run_cmd('mkfs.ext4 -m1 /dev/pve/data')
            run_cmd('mount /dev/pve/data /var/lib/vz')
            file_append("/etc/fstab", "/dev/pve/data /var/lib/vz ext4 defaults 0 2")

        # Mount Template CIFS-Share und importiere VMs
        #storage = "local"
        #if run_cmd('pvesh get /storage | grep -i local-lvm', argShell=True) == 0:
        #    storage = "local-lvm"
        #
        #if self.filesystem == "zfs":
        #    storage = "local-zfs"
        storage = self.storage_import

        if len(self.vm_import) > 0 or len(self.lxc_import) > 0:
            retval = gui_password_box("Samba Passwort benötigt", "Bitte das Passwort für Share " + VM_TEMPLATE_CIFS_SHARE + " und Benutzer " + VM_TEMPLATE_CIFS_USER + " eingeben.")
            VM_TEMPLATE_CIFS_PASS = retval[1]

            cifscnt = 1
            run_cmd('mkdir -p /mnt/proxmox-install-import', argShell=True)
            cifstest = run_cmd('mount -t cifs -o user=' + VM_TEMPLATE_CIFS_USER + ",password=" + VM_TEMPLATE_CIFS_PASS + " " + VM_TEMPLATE_CIFS_SHARE + ' /mnt/proxmox-install-import')
            while cifstest != 0 and cifscnt < 3:
                retval = gui_password_box("Passwort falsch, Samba Passwort benötigt", "Bitte das Passwort für Share " + VM_TEMPLATE_CIFS_SHARE + " und Benutzer " + VM_TEMPLATE_CIFS_USER + " erneut eingeben.")
                VM_TEMPLATE_CIFS_PASS = retval[1]
                cifstest = run_cmd('mount -t cifs -o user=' + VM_TEMPLATE_CIFS_USER + ",password=" + VM_TEMPLATE_CIFS_PASS + " " + VM_TEMPLATE_CIFS_SHARE + ' /mnt/proxmox-install-import')
                if cifstest == 0:
                    break
                cifscnt += 1

            if cifstest == 0:
                # Import selected VMs
                for vm_id in self.vm_import:
                    (ret, filename) = run_cmd_stdout("ls -t /mnt/proxmox-install-import/vzdump-qemu-%s*vma.zst | head -n1" % vm_id, argShell=True)
                    if filename != "":
                        run_cmd("qmrestore %s %s -storage %s" % (filename.strip(), vm_id, storage))
                        if self.VM_IMPORTS[vm_id]["template"] == True:
                            run_cmd("qm template %s" % vm_id)

                # Import selected LXCs
                for vm_id in self.lxc_import:
                    (ret, filename) = run_cmd_stdout("ls -t /mnt/proxmox-install-import/vzdump-lxc-%s-*.tar.zst | head -n1" % vm_id, argShell=True)
                    if filename != "":
                        run_cmd("pct restore %s %s -storage %s" % (vm_id, filename.strip(), storage))
                        if self.LXC_IMPORTS[vm_id]["template"] == True:
                            run_cmd("pct template %s" % vm_id)

                run_cmd('umount /mnt/proxmox-install-import')
            else:
                gui_message_box("Installer", "CIFS konnte nicht gemounted werden (Passwort falsch?), VMs werden nicht importiert!")

            VM_TEMPLATE_CIFS_PASS = ""

        # Apt-Proxy Cache
        if self.proxy == True:
            file_create("/etc/apt/apt.conf.d/01proxy", 'Acquire::http { Proxy "http://10.69.99.10:3142"; };')

        # Installieren allgemeine Tools und Monitoring-Agent
        run_cmd('apt-get update')
        apt_install('dirmngr')
        #file_create("/etc/apt/sources.list.d/iteas.list", "deb https://apt.iteas.at/iteas bullseye main")
        run_cmd('apt-key adv --recv-keys --keyserver keyserver.ubuntu.com 23CAE45582EB0928', argShell=True)
        run_cmd('wget https://apt.iteas.at/iteas-keyring.gpg -O /etc/apt/trusted.gpg.d/iteas-keyring.gpg', argShell=True)
        run_cmd('apt-get update')
        run_cmd('apt-get dist-upgrade -y')
        apt_install('dirmngr htop unp postfix sudo screen zsh tmux bwm-ng pigz sysstat ethtool nload apcupsd ntfs-3g sl gawk ca-certificates-iteas-enterprise at lsb-release lshw')
        # ifupdown2 nur installieren wenn nicht "noupdate" gewählt wurde da das Standard Paket in den Debian Quellen nicht mit Proxmox kompatibel ist
        if self.environment != "noupdate":
            apt_install('ifupdown2')

        if self.monitoring == "checkmk":
            apt_install('xinetd check-mk-agent')

        # Spezielle allgemeine Settings für ZFS
        if self.filesystem == "zfs":
            file_create("/etc/modprobe.d/zfs.conf", "options zfs zfs_arc_max=10737418240")
            run_cmd('update-initramfs -u', argShell=True)

        # SUDOers
        file_append("/etc/sudoers", "#backuppc      ALL=(ALL) NOPASSWD: /usr/bin/rsync")
        file_append("/etc/sudoers", "#backuppc      ALL=(ALL) NOPASSWD: /bin/tar")

        # Monitoring Konfiguration
        if self.monitoring == "checkmk":

            # Check-MK-Agent Config
            run_cmd('wget -O /tmp/mk_smart https://git.styrion.net/iteas/check_mk-smart-plugin/raw/master/agents/smart')
            run_cmd('mv /tmp/mk_smart /usr/lib/check_mk_agent/plugins/')
            run_cmd('wget -O /tmp/mk_apcupsd https://git.styrion.net/iteas/iteas-tools/raw/master/proxmox/usr/lib/check_mk_agent/plugins/mk_apcupsd')
            run_cmd('mv /tmp/mk_apcupsd /usr/lib/check_mk_agent/plugins/')
            run_cmd('wget -O /tmp/mk_dmi_sysinfo https://git.styrion.net/iteas/iteas-tools/raw/master/proxmox/usr/lib/check_mk_agent/plugins/mk_dmi_sysinfo')
            run_cmd('mv /tmp/mk_dmi_sysinfo /usr/lib/check_mk_agent/plugins/')
            run_cmd('wget -O /tmp/mk_inventory https://git.styrion.net/iteas/iteas-tools/raw/master/proxmox/usr/lib/check_mk_agent/plugins/mk_inventory')
            run_cmd('mv /tmp/mk_inventory /usr/lib/check_mk_agent/plugins/')
            run_cmd('wget -O /tmp/mk_lmsensors https://git.styrion.net/iteas/iteas-tools/raw/master/proxmox/usr/lib/check_mk_agent/plugins/mk_lmsensors')
            run_cmd('mv /tmp/mk_lmsensors /usr/lib/check_mk_agent/plugins/')
            run_cmd('wget -O /tmp/mk_logins https://git.styrion.net/iteas/iteas-tools/raw/master/proxmox/usr/lib/check_mk_agent/plugins/mk_logins')
            run_cmd('mv /tmp/mk_logins /usr/lib/check_mk_agent/plugins/')
            run_cmd('wget -O /tmp/mk_nfsexports https://git.styrion.net/iteas/iteas-tools/raw/master/proxmox/usr/lib/check_mk_agent/plugins/mk_nfsexports')
            run_cmd('mv /tmp/mk_nfsexports /usr/lib/check_mk_agent/plugins/')
            run_cmd('wget -O /tmp/mk_netstat https://git.styrion.net/iteas/iteas-tools/raw/master/proxmox/usr/lib/check_mk_agent/plugins/mk_netstat')
            run_cmd('mv /tmp/mk_netstat /usr/lib/check_mk_agent/plugins/')
            run_cmd('chmod +x /usr/lib/check_mk_agent/plugins/mk_*', argShell=True)

        # APC
        run_cmd('wget -O /etc/apcupsd/apcupsd.conf https://git.styrion.net/iteas/iteas-tools/raw/master/proxmox/etc/apcupsd.conf')
        file_replace_line("/etc/default/apcupsd", "ISCONFIGURED", "ISCONFIGURED=yes")
        run_cmd('systemctl enable apcupsd.service')

        # Nano
        run_cmd('wget -O /tmp/nano.tar https://git.styrion.net/iteas/iteas-tools/raw/master/proxmox/config/nano.tar')
        run_cmd('tar -xf /tmp/nano.tar -C /root')
        run_cmd('rm /tmp/nano.tar')

        # ZSH
        run_cmd('wget -O /tmp/zshrc_root https://git.styrion.net/iteas/iteas-tools/raw/master/proxmox/config/zshrc_root')
        run_cmd('mv /tmp/zshrc_root /root/.zshrc')
        file_replace_line("/root/.zshrc", "iteas.local", 'export PS1="%UDomain:%u %B%F{yellow}' + self.domain + ' $PS1"', encoding='iso8859_15')
        run_cmd('usermod -s /bin/zsh root')

        # Postfix
        file_replace_line("/etc/postfix/main.cf", "myhostname=", "myhostname=" + self.fqdn + ".monitoring.iteas.at")
        file_replace_line("/etc/postfix/main.cf", "relayhost =", "relayhost = smtp.styrion.net")
        run_cmd('systemctl restart postfix.service')

        # SystemD
        run_cmd('wget -O /etc/systemd/system/rc.local.shutdown.service https://git.styrion.net/iteas/iteas-tools/raw/master/proxmox/systemd/rc.local.shutdown.service')
        run_cmd('wget -O /etc/rc.local.shutdown https://git.styrion.net/iteas/iteas-tools/raw/master/proxmox/systemd/rc.local.shutdown')
        run_cmd('systemctl enable rc.local.shutdown.service')
        
        # USB-Automount (soll zur manuellen Auswahl stehen)
        # apt_install('pve6-usb-automount')

        # Kexec (funktioniert nicht)
        # run_cmd('echo "kexec-tools kexec-tools/load_kexec boolean false" | debconf-set-selections', argShell=True)
        # apt_install('kexec-tools')
        # run_cmd('wget -O /etc/systemd/system/kexec-pve.service https://git.styrion.net/iteas/iteas-tools/raw/master/proxmox/systemd/kexec-pve.service')
        #run_cmd('systemctl enable kexec-pve.service')

        # SysCTL
        file_create("/etc/sysctl.d/iteas.conf", "fs.inotify.max_user_watches=5242880")
        file_append("/etc/sysctl.d/iteas.conf", "fs.inotify.max_user_instances=1024")

        ############ Konfiguration für Backup-Server
        if self.machine_type == "backup":
            # NFS, Samba & ZFS
            apt_install('samba')

            #password = gui_password_verify_box("Samba Passwort", "Geben Sie das Passwort fuer den Samba Benutzer 'admin' an:", "Geben Sie das Passwort fuer den Samba Benutzer 'admin' erneut an:")
            password = SMB_ADMIN_PASSWD
            run_cmd("groupadd localbackup", argShell=True)
            run_cmd("useradd localbackup -m -g localbackup -p '%s'" % password, argShell=True)
            run_cmd("(echo '%s'; echo '%s') | smbpasswd -a localbackup" % (password, password), argShell=True)
            run_cmd('wget -O /etc/samba/smb.conf https://git.styrion.net/iteas/iteas-tools/raw/master/proxmox/samba/backup_default_smb2.conf')

            backup_root = ""
            if self.filesystem == "zfs":
                run_cmd('zfs create rpool/vollsicherung')
                apt_install('zfs-zed')
                file_replace_line("/etc/samba/smb.conf", "path = /var/lib/vz/vollsicherung", "\tpath = /rpool/vollsicherung")
                backup_root = "/rpool/vollsicherung"
            else:
                run_cmd('mkdir /var/lib/vz/vollsicherung')
                backup_root = "/var/lib/vz/vollsicherung"

            run_cmd("chown -R localbackup:localbackup %s" % backup_root)

            file_replace_line("/etc/samba/smb.conf", "workgroup = kundendomain.local", "\tworkgroup = %s" % self.domain)
            if len(self.share_clients) > 0:
                file_replace_line("/etc/samba/smb.conf", "hosts allow =", "\thosts allow = %s" % " ".join(self.share_clients))

            run_cmd('systemctl enable smbd')
            run_cmd('systemctl start smbd')

            # Webmin
            file_create("/etc/apt/sources.list.d/webmin.list", "deb https://download.webmin.com/download/repository sarge contrib")
            run_cmd("cd /tmp && wget http://www.webmin.com/jcameron-key.asc && apt-key add jcameron-key.asc", argShell=True)
            apt_install("apt-transport-https curl git")
            run_cmd("apt-get update", argShell=True)
            apt_install("webmin")
            file_append("/etc/webmin/config", "lang_root=de.UTF-8")
            file_append("/etc/webmin/config", "theme_root=authentic-theme")
            file_replace_line("/etc/webmin/config", "lang=", "lang=de.UTF-8")
            file_append("/etc/webmin/miniserv.conf", "preroot_root=authentic-theme")
            run_cmd('mkdir /etc/webmin/authentic-theme')
            run_cmd('wget -O /etc/webmin/authentic-theme/favorites.json https://git.styrion.net/iteas/iteas-tools/raw/master/proxmox/webmin/favorites.json')
            run_cmd('systemctl restart webmin')


        ############  Konfiguration für HP < Gen10
        if self.machine_vendor == "hp":
            # HP-Tools
            file_create("/etc/apt/sources.list.d/hp.list", "deb http://downloads.linux.hpe.com/SDR/downloads/MCP bullseye/current non-free")
            file_append("/etc/apt/sources.list.d/hp.list", "deb http://downloads.linux.hpe.com/SDR/downloads/MCP/debian bullseye/current non-free")
            run_cmd('apt-key adv --recv-keys --keyserver keyserver.ubuntu.com 527BC53A2689B887')
            run_cmd('apt-key adv --recv-keys --keyserver keyserver.ubuntu.com FADD8D64B1275EA3')
            run_cmd('apt-key adv --recv-keys --keyserver keyserver.ubuntu.com C208ADDE26C2B797')
            run_cmd('apt-key adv --recv-keys --keyserver keyserver.ubuntu.com 26C2B797')
            run_cmd('apt-get update')
            apt_install('ssacli hponcfg')
            run_cmd('ln -s /usr/sbin/ssacli /usr/sbin/hpacucli')

        ############ Konfiguration für HP Gen10
        elif self.machine_vendor == "hp10":
            # HP-Tools
            file_create("/etc/apt/sources.list.d/hp.list", "deb http://downloads.linux.hpe.com/SDR/downloads/MCP buster/current non-free")
            file_append("/etc/apt/sources.list.d/hp.list", "deb http://downloads.linux.hpe.com/SDR/downloads/MCP/debian buster/current non-free")
            run_cmd('apt-key adv --recv-keys --keyserver keyserver.ubuntu.com 527BC53A2689B887')
            run_cmd('apt-key adv --recv-keys --keyserver keyserver.ubuntu.com FADD8D64B1275EA3')
            run_cmd('apt-key adv --recv-keys --keyserver keyserver.ubuntu.com C208ADDE26C2B797')
            run_cmd('apt-key adv --recv-keys --keyserver keyserver.ubuntu.com 26C2B797')
            run_cmd('apt-get update')
            apt_install('ssacli hponcfg binutils')
            run_cmd('ln -s /usr/sbin/ssacli /usr/sbin/hpacucli')

        elif self.machine_vendor == "tk":
            # IPMI Tools
            apt_install('ipmitool ipmiutil')

        # Configure IPMI
        if self.ipmi_config:
            # Thanks TK-Wiki: https://www.thomas-krenn.com/de/wiki/IPMI_Konfiguration_unter_Linux_mittels_ipmitool
            run_cmd('ipmitool lan set 1 ipsrc static', argShell=True)
            run_cmd('ipmitool lan set 1 ipaddr "%s"' % self.ipmi_ip, argShell=True)
            run_cmd('ipmitool lan set 1 netmask "%s"' % self.ipmi_netmask, argShell=True)
            run_cmd('ipmitool lan set 1 defgw ipaddr "%s"' % self.ipmi_gateway, argShell=True)
            run_cmd('ipmitool user set name 2 "%s"' % self.ipmi_user, argShell=True)
            run_cmd('ipmitool user set password 2 "%s"' % self.ipmi_pass, argShell=True)
            run_cmd('ipmitool channel setaccess 1 2 link=on ipmi=on callin=on privilege=4', argShell=True)
            run_cmd('ipmitool user enable 2', argShell=True)

        # Install puppet
        if self.puppet == "generic":
            run_cmd('wget -O /tmp/install_puppet.sh https://git.styrion.net/iteas/iteas-tools/raw/master/puppet/proxmox_mit_puppet.sh && chmod +x /tmp/install_puppet.sh', argShell=True)
            run_cmd('echo "\n" | /tmp/install_puppet.sh', argShell=True)
        elif self.puppet == "proxmox-desktop":
            run_cmd('wget -O /tmp/install_puppet.sh https://git.styrion.net/iteas/iteas-tools/raw/master/puppet/proxmox_mit_puppet.sh && chmod +x /tmp/install_puppet.sh', argShell=True)
            run_cmd('echo "\n" | /tmp/install_puppet.sh', argShell=True)

        # Desktop Konfiguration
        if self.desktop == "plasma-light":
            apt_install('lm-sensors curl nomachine firefox-esr firefox-esr-l10n-de virt-viewer kde-plasma-desktop qapt-deb-installer filelight khelpcenter mpv curl task-german-kde-desktop task-german hunspell-de-at hunspell-de-ch hyphen-de mythes-de-ch mythes-de git kate')
            run_cmd('wget -O /tmp/KDE_Plasma5_Default_Profile-Proxmox5.tar.gz https://git.styrion.net/iteas/iteas-tools/raw/master/proxmox/KDE_Plasma5_Default_Profile-Proxmox5.tar.gz')
            run_cmd('rm -rf /etc/skel', argShell=True)
            run_cmd('tar -xzf /tmp/KDE_Plasma5_Default_Profile-Proxmox5.tar.gz -C /etc', argShell=True)
            run_cmd('mv /etc/KDE_Plasma5_Default_Profile-master /etc/skel', argShell=True)
            run_cmd('rm /tmp/KDE_Plasma5_Default_Profile-Proxmox5.tar.gz', argShell=True)
            run_cmd('useradd iteasadm -c iteasadm -G dialout,cdrom,video,plugdev,games,sudo -m -s /bin/zsh -U -p \'$1$CvBQaSeR$0phJus.ly543oq2fKOtT40\'', argShell=True)

        elif self.desktop == "plasma-light-win":
            apt_install('lm-sensors curl nomachine firefox-esr firefox-esr-l10n-de virt-viewer kde-plasma-desktop qapt-deb-installer filelight khelpcenter mpv curl task-german-kde-desktop task-german hunspell-de-at hunspell-de-ch hyphen-de mythes-de-ch mythes-de git kate')
            run_cmd('apt remove -y konqueror', argShell=True)
            run_cmd('wget -O /tmp/KDE_Plasma5_Default_Profile-Proxmox5.tar.gz https://git.styrion.net/iteas/iteas-tools/raw/master/proxmox/KDE_Plasma5_Default_Profile-Proxmox5.tar.gz')
            run_cmd('rm -rf /etc/skel', argShell=True)
            run_cmd('tar -xzf /tmp/KDE_Plasma5_Default_Profile-Proxmox5.tar.gz -C /etc', argShell=True)
            run_cmd('mv /etc/KDE_Plasma5_Default_Profile-master /etc/skel', argShell=True)
            run_cmd('rm /tmp/KDE_Plasma5_Default_Profile-Proxmox5.tar.gz', argShell=True)
            run_cmd('pveum user add user@pve', argShell=True)
            run_cmd('echo "123123\n123123" | pveum passwd user@pve', argShell=True)
            run_cmd('useradd user -c user -G dialout,cdrom,video,plugdev,games -m -s /bin/zsh -U -p \'$1$bXXXRpOf$cLs.kEex6rSD8horkJzru0\'', argShell=True)
            run_cmd('wget -O /etc/sddm.conf https://git.styrion.net/iteas/iteas-tools/raw/master/proxmox/etc/sddm.conf-user-autologon')
            run_cmd('cd /tmp && git clone https://gitlab+deploy-token-1:-9F-Ty1feEf-9sQy_if4@git.styrion.net/iteas/proxmox-workstation.git && rm -rf /home/user && cp -r proxmox-workstation /home/user && chown -R user:user /home/user', argShell=True)
            run_cmd('pvesm set local -disable', argShell=True)

        elif self.desktop == "plasma":
            apt_install('lm-sensors curl nomachine firefox-esr firefox-esr-l10n-de virt-viewer kde-plasma-desktop qapt-deb-installer filelight khelpcenter mpv curl task-german-kde-desktop task-german hunspell-de-at hunspell-de-ch hyphen-de mythes-de-ch mythes-de git kde-standard plasma-desktop task-german-desktop libreoffice-l10n-de mpv muon speedtest-cli x2goclient filezilla mactelnet-client ksystemlog kate gtkterm sddm-theme-debian-breeze')
            run_cmd('wget -O /tmp/KDE_Plasma5_Default_Profile-Proxmox5.tar.gz https://git.styrion.net/iteas/iteas-tools/raw/master/proxmox/KDE_Plasma5_Default_Profile-Proxmox5.tar.gz')
            run_cmd('rm -rf /etc/skel', argShell=True)
            run_cmd('tar -xzf /tmp/KDE_Plasma5_Default_Profile-Proxmox5.tar.gz -C /etc', argShell=True)
            run_cmd('mv /etc/KDE_Plasma5_Default_Profile-master /etc/skel', argShell=True)
            run_cmd('rm /tmp/KDE_Plasma5_Default_Profile-Proxmox5.tar.gz', argShell=True)
            run_cmd('useradd iteasadm -c iteasadm -G dialout,cdrom,video,plugdev,games,sudo -m -s /bin/zsh -U -p \'$1$CvBQaSeR$0phJus.ly543oq2fKOtT40\'', argShell=True)

        elif self.desktop == "i3":
            pass

        run_cmd('apt-get install -f; apt autoremove --purge -y;', argShell=True)
        if self.proxy == True:
            run_cmd('rm /etc/apt/apt.conf.d/01proxy')

        # Install Proxmox Config Backup Script
        B_SCRIPT = """#!/bin/bash

usage() { echo "Usage: $0 [-p <backup_path>]" 1>&2; exit 1; }

while getopts ":p:" o; do
    case "${o}" in
        p)
            p=${OPTARG}
            ;;
        *)
            usage
            ;;
    esac
done
shift $((OPTIND-1))

B_PATH="${p:-/root/}"
echo "Sichere Backup in $B_PATH"
tar -cf "$B_PATH`hostname -f`-backup.tar" /etc /root
"""
        file_create("/usr/local/bin/backup-proxmox-config", B_SCRIPT)
        run_cmd('chmod +x /usr/local/bin/backup-proxmox-config')

        sum_txt = """-------------------------------------------------------------------------------
ITEAS Proxmox Installationsbericht

Loginmoeglichkeiten:
  https://%s:8006 -> Weboberflaeche Virtualisierung
""" % check_systemip(show_prefix=False)

        if self.machine_type == "backup":
            sum_txt += "  https://%s:10000 -> Weboberflaeche Webmin (NFSfreigaben, Samba, etc.)" % check_systemip(show_prefix=False)


        sum_txt += """
  SSH ueber CMD f.e "ssh root@%s"

Folgende lokale Benutzer wurden angelegt:
  root (Administrator) SSH, Virtualisierung, Webmin
""" % check_systemip(show_prefix=False)

        if self.machine_type == "backup":
            sum_txt += "  backup (fuer den Zugriff auf Freigaben) Samba"

        sum_txt += """

Das Komplette Installationslog ist auf
  /var/log/proxmox_install.log einsehbar.
-------------------------------------------------------------------------------
"""

        fr = open("/root/proxmox_report.txt", "w")
        fr.write(sum_txt)
        fr.close()

        gui_text_box("/root/proxmox_report.txt")

        # Installation fertig
        retval = gui_yesno_box("Installer", "Die Installation wurde abgeschlossen! Moechten Sie den PC/Server neustarten?")
        if retval[0] == 0:
            pbox = gui_progress_box("PC/Server wird automatisch neugestartet...", 0)
            for x in range(0, 5):
                pbox.update(x*20)
                time.sleep(1)

            pbox.finish()
            run_cmd('reboot')
        elif retval[0] == 1:
            gui_message_box("Installer", "Sie muessen den PC/Server manuell neustarten um die Installation abzuschliessen!")


i = Installer()
i.start()
logger.close()
