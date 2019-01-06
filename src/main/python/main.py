from fbs_runtime.application_context import ApplicationContext

import sys

from gemino import MainWindow


class AppContext(ApplicationContext):  # 1. Subclass ApplicationContext
    def run(self):  # 2. Implement run()
        window = MainWindow()
        version = self.build_settings['version']
        window.setWindowTitle("gemino v" + version)
        window.resize(650, 600)
        window.show()
        return self.app.exec_()  # 3. End run() with this line


if __name__ == '__main__':
    appctxt = AppContext()  # 4. Instantiate the subclass
    exit_code = appctxt.run()  # 5. Invoke run()
    sys.exit(exit_code)
