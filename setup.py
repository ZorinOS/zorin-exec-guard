from distutils.core import setup
from DistUtilsExtra.command import *

class zorin_exec_guard_build_i18n(build_i18n.build_i18n):
    def run(self):
         build_i18n.build_i18n.run(self)

setup(
    name='zorin-exec-guard',
    version='1.0',
    url='http://zorinos.com',
    author='Zorin OS Technologies Ltd.',
    author_email='os@zoringroup.com',
    description='Zorin Exec Guard',
    long_description=("Zorin Exec Guard shows a warning when attempting to run unknown Linux or Windows executables and offers more trusted alternatives."),
    license='GPL-3.0',

    packages=['zorin_exec_guard'],
    package_dir={'zorin_exec_guard': 'zorin_exec_guard'},
    scripts=['bin/zorin-exec-guard-linux','bin/zorin-exec-guard-windows'],
    cmdclass = { "build" : build_extra.build_extra,
        "build_i18n" :  zorin_exec_guard_build_i18n,
        "clean": clean_i18n.clean_i18n,
    }
)
