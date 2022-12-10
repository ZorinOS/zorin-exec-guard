# This file is part of the Zorin Exec Guard program.
#
# Copyright 2018-2022 Zorin OS Technologies Ltd.
#
# This program is free software you can redistribute it and/or modify it
# under the terms and conditions of the GNU General Public License,
# version 3, as published by the Free Software Foundation.
#
# This program is distributed in the hope it will be useful, but WITHOUT ANY
# WARRANTY without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.  See the GNU Lesser General Public License for
# more details.


import gi
import gettext
import re
import json
import sys
import logging

gi.require_version('Gtk', '3.0')
gi.require_version('Flatpak', '1.0')
from gi.repository import Gtk, Gio, GLib, Flatpak, GObject

import apt
from aptdaemon.client import AptClient
from aptdaemon.gtk3widgets import AptErrorDialog, AptProgressDialog
import aptdaemon.errors
from aptdaemon.enums import *

t = gettext.translation('zorin-exec-guard', '/usr/share/locale',
                        fallback=True)
_ = t.gettext

MAX_EXEC_CHAR_LENGTH = 12
APP_DB_FILE = "/usr/share/zorin-exec-guard/app_db.json"


def title(text):
    return '<big><b>%s</b></big>' % text
    
def truncate_with_ellipses(text, max):
    prefix = text[0:-3]
    suffix = text[-3:len(text)]
    ellipsis = '...' if len(prefix) > max else ''
    return prefix[0:max-1] + ellipsis + suffix


class ExecGuardApplication(Gtk.Application):

    def __init__(self, props):
        super(Gtk.Application, self).__init__(application_id=self.APP_ID)

        self.executable = props["executable"]
        self.platform = props["platform"]

        self.app_db = []
        try:
            with open(APP_DB_FILE) as file:
                self.app_db = json.load(file)
        except:
            pass

        self.replacement = find_replacement(self.executable["filename"],
                                            self.platform,
                                            self.app_db)

        self._installed_replacement_flatpak_ref = None
        if self.replacement and "flatpak" in self.replacement:
            self._installed_replacement_flatpak_ref = get_installed_flatpak_ref(self.replacement["flatpak"]["id"])

        self._installed_replacement_apt_package = None
        if self.replacement and "apt" in self.replacement and is_apt_package_installed(self.replacement["apt"]):
            self._installed_replacement_apt_package = self.replacement["apt"]

        self._replacement_desktop_launcher = None
        if self.replacement and "desktopLauncher" in self.replacement:
            try:
                self._replacement_desktop_launcher = Gio.DesktopAppInfo.new(self.replacement["desktopLauncher"])
            except:
                pass

        self._replacement_installed = self.replacement and (self._replacement_desktop_launcher or ("flatpak" in self.replacement and self._installed_replacement_flatpak_ref) or self._installed_replacement_apt_package or "webLink" in self.replacement)

    def do_startup(self):
        Gtk.Application.do_startup(self)

        action = Gio.SimpleAction.new("quit", None)
        action.connect("activate", self.on_quit)
        self.add_action(action)

        self._create_window()

    def do_activate(self):
        self.window.present()

    def on_quit(self, action, param):
        self.quit()

    def _on_quit_handler(self, object):
        self.quit()

    def _launch_executable(self, widget):
        pass

    def launch_replacement_app(self, widget):
        self._launch_peferred_app()
        self.quit()
        
    def _launch_peferred_app(self):
        if "steam" in self.replacement:
            launch_steam_app(self.replacement)
            return

        if self._replacement_desktop_launcher:
            launch_desktop_app(self._replacement_desktop_launcher)
            return

        if "webLink" in self.replacement:
            launch_link(self.replacement)
            return
            
        if "flatpak" in self.replacement:
            launch_flatpak_app(self.replacement)
            return
    
    def install_replacement_app(self, widget):
        if "apt" in self.replacement:
            self.window.hide()
            package_install = AptInstallation(self.replacement)
            package_install.connect("finished", self._on_quit_handler)
            package_install.run()
        else:
            install_app_from_software(self.replacement)
            self.quit()
            
    def _get_main_message(self):
        if not self.replacement:
            return _("Are you sure you want to run %s?") % truncate_with_ellipses(self.executable["filename"], MAX_EXEC_CHAR_LENGTH*4)

        if "mainMessage" in self.replacement:
            return self.replacement["mainMessage"]

        if "steam" in self.replacement:
            return _("%s is available on Steam") % self.replacement["name"]

        name = self.replacement["alternative"]["name"] if "alternative" in self.replacement else self.replacement["name"]

        if self._replacement_installed:
            return _("%s is already installed") % name

        return _("%s can be installed from Software") % name

    def _get_app_alternative_message(self):
        if self.replacement and "alternative" in self.replacement:
            return _("%s is an alternative to %s.") % (self.replacement["alternative"]["name"], self.replacement["name"])
        else:
            return None

    def _get_unknown_app_warning_message(self):
        frame = Gtk.Frame(visible=True)
        text_view = Gtk.TextView(visible=True,
                                 editable=False,
                                 cursor_visible=False,
                                 top_margin=8,
                                 left_margin=8,
                                 bottom_margin=8,
                                 right_margin=8,
                                 wrap_mode=Gtk.WrapMode.WORD)
        text_buffer = text_view.get_buffer()

        escaped_filename = truncate_with_ellipses(GLib.markup_escape_text(self.executable["filename"], -1), MAX_EXEC_CHAR_LENGTH*3)
        text = _("%s is an unknown package.") % escaped_filename + "\n\n" + _("Your computer and personal data may be vulnerable to a breach when running apps from unknown sources.")

        text_buffer.set_text(text, -1)

        frame.add(text_view)

        return frame

    def _get_links(self, box):
        pass

    def _get_buttons(self, box):
        button = None
        application = self

        if not self.replacement:
            button = Gtk.Button.new_from_stock(Gtk.STOCK_CANCEL)
            button.connect('clicked', application._on_quit_handler)
            box.add(button)
            return

        # For libraries like Flash Player which don't have launchers
        if "noButton" in self.replacement or (self._replacement_installed and (not "desktopLauncher" in self.replacement) and (not "flatpak" in self.replacement) and (not "webLink" in self.replacement)):
            button = Gtk.Button.new_from_stock(Gtk.STOCK_OK)
            button.connect('clicked', application._on_quit_handler)
            box.add(button)
            return

        name = self.replacement["alternative"]["name"] if "alternative" in self.replacement else self.replacement["name"]

        if self._replacement_installed:
            button = Gtk.Button(visible=True, label=_("Launch %s") % name)
            button.connect('clicked', application.launch_replacement_app)
            button.get_style_context().add_class('suggested-action')
            box.add(button)
            return
        else:
            button = Gtk.Button(visible=True, label=_("Install %s") % name)
            button.connect('clicked', application.install_replacement_app)
            button.get_style_context().add_class('suggested-action')
            box.add(button)
            return

    def _create_window(self):
        self.window = Gtk.ApplicationWindow(application=self,
                                            title=truncate_with_ellipses(self.executable["filename"], MAX_EXEC_CHAR_LENGTH*4),
                                            skip_taskbar_hint=True,
                                            resizable=False)
        self.window.set_position(Gtk.WindowPosition.CENTER)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,
                      margin=18,
                      spacing=18,
                      visible=True)
        self.window.add(box)

        information_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,
                                   halign=Gtk.Align.START,
                                   hexpand=True,
                                   margin_left=18,
                                   spacing=36)

        icon = Gio.ThemedIcon(name="dialog-warning-symbolic")
        image = Gtk.Image.new_from_gicon(icon, Gtk.IconSize.DIALOG)
        image.set_valign(Gtk.Align.START)
        information_box.add(image)

        message_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,
                              valign=Gtk.Align.START,
                              spacing=18)

        label = Gtk.Label(use_markup=True,
                                wrap=True,
                                max_width_chars=40,
                                halign=Gtk.Align.CENTER,
                                label=title(self._get_main_message()))
        message_box.add(label)

        app_alternative_message = self._get_app_alternative_message()
        if app_alternative_message:
            label = Gtk.Label(use_markup=True,
                                    wrap=True,
                                    max_width_chars=40,
                                    halign=Gtk.Align.START,
                                    label=app_alternative_message )
            message_box.add(label)

        message_box.add(self._get_unknown_app_warning_message())
        information_box.add(message_box)
        box.add(information_box)

        actions_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,
                              halign=Gtk.Align.END,
                              spacing=6)
        box.pack_end(actions_box, False, True, 0)

        link_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,
                           halign=Gtk.Align.START,
                           spacing=6)
        self._get_links(link_box)
        actions_box.pack_start(link_box, False, False, 0)

        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,
                             halign=Gtk.Align.END,
                             spacing=6)
        self._get_buttons(button_box)
        actions_box.pack_end(button_box, False, False, 0)

        self.window.show_all()


class AptInstallation(GObject.GObject):

    __gsignals__ = {"finished": (GObject.SIGNAL_RUN_FIRST,
                                 GObject.TYPE_NONE,
                                 ())
                   }

    def __init__ (self, replacement):
        GObject.GObject.__init__(self)

        self.replacement = replacement
        self.apt_client = AptClient()

    def run(self):
        apt_cache = open_apt_cache()

        if not apt_cache.has_key(self.replacement["apt"]):
            self.do_update()
        else:
            self.do_install()

    def do_update(self):
        trans_update = self.apt_client.update_cache()
        trans_update.connect("finished", self.on_finished_update)

        dia = AptProgressDialog(trans_update)
        dia.run(close_on_finished=True,
                show_error=False,
                reply_handler=lambda: True,
                error_handler=self.on_error)
        return

    def on_finished_update(self, trans, exit):
        if exit == "exit-success":
            GLib.timeout_add(200, self.do_install)
        return True

    def do_install(self):
        trans_inst = self.apt_client.install_packages(package_names=[self.replacement["apt"]])
        trans_inst.connect("finished", self.on_finished_install)
        dia = AptProgressDialog(transaction=trans_inst)
        dia.connect("finished", self.on_install_dialog_finished)
        dia.run(close_on_finished=True,
                show_error=False,
                reply_handler=lambda: True,
                error_handler=self.on_error)
        return

    def on_install_dialog_finished(self, dia):
        if self.exit == "exit-success":
            try:
                replacement_desktop = Gio.DesktopAppInfo.new(self.replacement["desktopLauncher"])
                launch_desktop_app(replacement_desktop)
            except:
                installed_package_name = self.replacement["name"]
                if "alternative" in self.replacement:
                    installed_package_name = self.replacement["alternative"]["name"]
                self.finished_dialog(_("%s has been installed") % installed_package_name)

        self.emit("finished")

    def on_finished_install(self, trans, exit):
        self.exit = exit
        return

    def finished_dialog(self, message):
        dialog = Gtk.MessageDialog(message_type=Gtk.MessageType.INFO,
                                   buttons=Gtk.ButtonsType.OK,
                                   text=message)
        dialog.run()
        dialog.destroy()
        return

    def on_error(self, error):
        if isinstance(error, aptdaemon.errors.NotAuthorizedError):
            # Silently ignore auth failures
            return
        elif not isinstance(error, aptdaemon.errors.TransactionFailed):
            # Catch internal errors of the client
            error = aptdaemon.errors.TransactionFailed(ERROR_UNKNOWN,str(error))
        dia = AptErrorDialog(error)
        dia.run()
        dia.hide()


def spawn_process(args=[]):
    return Gio.Subprocess.new(args, Gio.SubprocessFlags.NONE)

def get_software_app_id(replacement):
    app_id = None

    if "flatpak" in replacement:
        app_id = replacement["flatpak"]["id"]

        if "remote" in replacement["flatpak"]:
            remote = replacement["flatpak"]["remote"]
            installation = Flatpak.Installation.new_system(None)
            flatpak_remote = None

            try:
                flatpak_remote = installation.get_remote_by_name(remote, None)
            except:
                e = sys.exc_info()[0]
                logging.exception('Could not find flatpak remote %s: %s' % (remote, e))

            if flatpak_remote:
                default_branch = flatpak_remote.get_default_branch()
                if default_branch:
                    return 'system/flatpak/%s/desktop/%s.desktop/%s' % (remote, app_id, default_branch)
    elif "appstream" in replacement:
        app_id = replacement["appstream"]["id"]
    else:
        app_id = replacement["alternative"]["name"] if "alternative" in replacement else replacement["name"]

    return app_id

def install_app_from_software(replacement):
    software_app_id = get_software_app_id(replacement)
    Gio.DBusActionGroup.get(Gio.Application.get_default().get_dbus_connection(),
                            'org.gnome.Software',
                            '/org/gnome/Software').activate_action('details',
                            GLib.Variant('(ss)', (software_app_id, '')))

def get_installed_flatpak_ref(app_id):
    try:
        return Flatpak.Installation.new_user(None).get_current_installed_app(app_id, None)
    except:
        pass
        
    try:
        return Flatpak.Installation.new_system(None).get_current_installed_app(app_id, None)
    except:
        return None

def is_apt_package_installed(pkg):
    apt_cache = open_apt_cache()
    return apt_cache.has_key(pkg) and apt_cache[pkg].is_installed

def open_apt_cache():
    apt_cache = None
    try:
        apt_cache = apt.Cache()
    except SystemError as strerr:
        if not '/etc/apt/sources.list' in str(strerr):
            raise
        dialog = Gtk.MessageDialog(message_type=Gtk.MessageType.ERROR,
                                   buttons=Gtk.ButtonsType.OK,
                                   text="Invalid /etc/apt/sources.list file")
        dialog.format_secondary_text(strerr)
        dialog.run()
        dialog.destroy()
        sys.exit(0)
    if apt_cache._depcache.broken_count > 0:
        err_header = "Software index is broken"
        err_body = "This is a major failure of your software "
        "management system. Please check for broken packages "
        "with synaptic, check the file permissions and "
        "correctness of the file '/etc/apt/sources.list' and "
        "reload the software information with: "
        "'sudo apt-get update' and 'sudo apt-get install -f'."
        dialog = Gtk.MessageDialog(message_type=Gtk.MessageType.ERROR,
                                   buttons=Gtk.ButtonsType.OK,
                                   text=err_header)
        dialog.format_secondary_text(err_body)
        dialog.run()
        dialog.destroy()
        sys.exit(0)
    return apt_cache

def launch_flatpak_app(replacement):
    try:
        desktop_id = replacement["flatpak"]["id"] + '.desktop'
        desktop_launcher = Gio.DesktopAppInfo.new(desktop_id)
        desktop_launcher.launch([], None)
    except:
        e = sys.exc_info()[0]
        logging.exception('Something went wrong in launching %s: %s' % (replacement["flatpak"]["id"], e))

def launch_steam_app(replacement):
    try:
        spawn_process(['steam', '-applaunch', replacement["steam"]])
    except:
        e = sys.exc_info()[0]
        logging.exception('Something went wrong in launching %s: %s' % (replacement["steam"], e))

def launch_desktop_app(replacement_desktop):
    try:
        replacement_desktop.launch([], None)
    except:
        e = sys.exc_info()[0]
        logging.exception('Something went wrong in launching %s: %s' % (replacement, e))

def launch_link(replacement):
    try:
        Gio.AppInfo.launch_default_for_uri(replacement["webLink"]["href"], None)
    except:
        e = sys.exc_info()[0]
        logging.exception('Something went wrong in launching %s: %s' % (replacement["webLink"]["href"], e))

def find_replacement(filename, platform, app_db):
    for app in app_db:
        if platform in app["regex"]:
            pattern = re.compile(app["regex"][platform], re.IGNORECASE)
            if pattern.match(filename):
                return app

    return None

def get_executable(argv):
    executable_path = argv[1]
    if not executable_path:
        return None

    filename = GLib.path_get_basename(executable_path)

    return { "path": executable_path,
             "filename": filename }
