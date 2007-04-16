##########################################################################
# z3c.sqlalchemy - A SQLAlchemy wrapper for Python/Zope
#
# (C) Zope Corporation and Contributor
# Written by Andreas Jung for Haufe Mediengruppe, Freiburg, Germany
# and ZOPYX Ltd. & Co. KG, Tuebingen, Germany
##########################################################################


"""
Utility methods for SqlAlchemy
"""

import new
import threading

from sqlalchemy import Table, mapper, BoundMetaData, relation

marker = object


class MappedClassBase(object):
    """ base class for all mapped classes """

    def __init__(self, **kw):
        """ accepts keywords arguments used for initialization of
            mapped attributes/columns.
        """

        for k,v in kw.items():
            setattr(self, k, v)


class MapperFactory(object):
    """ a factory for table and mapper objects """

    def __init__(self, metadata):
        self.metadata = metadata

    def __call__(self, table, properties={}, cls=None):
        """ Returns a tuple (mapped_class, table_class).
            'table' - sqlalchemy.Table to be mapped
            'properties' - dict containing additional informations about
                           relationships etc (see sqlalchemy.Mapper docs)
            'cls' - (optional) class used as base for creating the mapper 
                    class (will be autogenerated if not available).
        """ 

        if cls is None:
            newCls = new.classobj('_mapped_%s' % table.name, (MappedClassBase,), {})
        else:
            newCls = cls

        mapper(newCls, table, properties=properties)
        return newCls



class LazyMapperCollection(dict):
    """ Implements a cache for table mappers """

    def __init__(self, wrapper):
        super(LazyMapperCollection, self).__init__()
        self._wrapper = wrapper
        self._engine = wrapper.engine
        self._model = wrapper.model or {}
        self._metadata = BoundMetaData(self._engine)
        self._mapper_factory = MapperFactory(self._metadata)
        self._dependent_tables = None
        self._lock = threading.Lock()


    def getMapper(self, name, schema='public'):
        """ return a (cached) mapper class for a given table 'name' """

        if not self.has_key(name):

            # no-cached data, let's lookup the table ourselfs
            table = None

            # check if the optional model provides a table definition
            if self._model.has_key(name):            
                table = self._model[name].get('table')

            # if not: introspect table definition
            if table is None:
                table = Table(name, self._metadata, autoload=True)

            # check if the model contains an optional mapper class
            mapper_class = None
            if self._model.has_key(name):            
                mapper_class = self._model[name].get('mapper_class')


            # use auto-introspected table dependencies for creating
            # the 'properties' dict that tells the mapper about
            # relationships to other tables 

            dependent_table_names = []
            if self._model.has_key(name):

                if self._model[name].get('relations') != None:
                    dependent_table_names = self._model[name].get('relations', []) or []
                elif self._model[name].get('autodetect_relations', False) == True:

                    if self._dependent_tables is None:
                        # Introspect table dependencies once. The introspection
                        # is deferred until the moment where we really need to 
                        # introspect them
                        if hasattr(self._wrapper, 'findDependentTables'):
                            self._dependent_tables = self._wrapper.findDependentTables(ignoreErrors=True)
                        else:
                            self._dependent_tables = {}

                    dependent_table_names = self._dependent_tables.get(name, []) or []
                
            # build additional property dict for mapper
            properties = {}

            # find all dependent tables (referencing the current table)
            for table_refname in dependent_table_names:

                # create or get a mapper for the referencing table
                table_ref_mapper = self.getMapper(table_refname)

                # add the mapper as relation to the properties dict
                properties[table_refname] = relation(table_ref_mapper)
       
            # create a mapper and cache it 
            mapper =  self._mapper_factory(table, 
                                           properties=properties, 
                                           cls=mapper_class)
            self.registerMapper(mapper, name)

        return self[name]


    def registerMapper(self, mapper, name):
        """ register a mapper under a given name """
    
        self._lock.acquire()
        self[name] = mapper
        self._lock.release()
