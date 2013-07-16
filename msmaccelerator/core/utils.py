import os
import shutil


class cd_context(object):
    """Context manager for cd
    """
    def __init__(self, dir, cleanup=True, logger=None):
        self.dir = dir
        self.cleanup = cleanup
        self.logger = logger

        # configured inside __enter__
        self.curdir = None
        self.path = None

    def __enter__(self):
        self.curdir = os.path.abspath(os.curdir)
        self.path = os.path.join(self.curdir, self.dir)

        if os.path.exists(self.path):
            raise IOError('path "%s" exists' % self.path)
        else:
            os.makedirs(self.path)

        os.chdir(self.path)
        self.log('Changing directory to %s' % self.path)

    def __exit__(self, *exc_info):
        os.chdir(self.curdir)
        self.log('Restoring directory to %s' % self.curdir)
        if self.cleanup:
            shutil.rmtree(self.path)
            self.log('Cleaning up directory %s' % self.path)

    def log(self, msg):
        if self.logger is not None:
            self.logger.info(msg)
        else:
            print msg
