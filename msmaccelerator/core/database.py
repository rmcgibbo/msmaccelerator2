##############################################################################
# Imports
##############################################################################
import functools
from threading import Lock

import sqlalchemy.exc
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, DateTime

##############################################################################
# Globals
##############################################################################

_Base = declarative_base()
_session_lock = Lock()
session = scoped_session(sessionmaker())


##############################################################################
# Models
##############################################################################


class Model(_Base):
    __tablename__ = 'models'

    id = Column(Integer, primary_key=True)
    time = Column(DateTime)
    protocol = Column(String(500))
    path = Column(String(500))
    
    def __str__(self):
        return "<Model path=%s>" % self.path

class Trajectory(_Base):
    __tablename__ = 'trajectories'
    
    id = Column(Integer, primary_key=True)
    time = Column(DateTime)
    protocol = Column(String(500))
    path = Column(String(500))


##############################################################################
# Functions and stuff
##############################################################################


def connect_to_sqlite_db(db_path):
    engine = create_engine('sqlite:///{}'.format(db_path), echo=False)
    session.configure(bind=engine)
    _Base.metadata.create_all(engine)


def with_db_lock(f):
    @functools.wraps(f)
    def wrap(*args, **kwargs):
        _session_lock.acquire()
        try:
            return f(*args, **kwargs)
        finally:
            _session_lock.release()
    return wrap