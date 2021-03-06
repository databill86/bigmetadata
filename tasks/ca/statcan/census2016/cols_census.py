import os
import json
from luigi import Parameter
from collections import OrderedDict
from tasks.base_tasks import ColumnsTask
from tasks.tags import SectionTags, SubsectionTags, UnitTags, PublicTags
from tasks.ca.statcan.license import LicenseTags, SourceTags
from tasks.meta import OBSColumn, DENOMINATOR, UNIVERSE
from lib.columns import ColumnsDeclarations


def load_definition():
    with open(os.path.join(os.path.dirname(__file__), 'census_columns.json')) as json_file:
        return json.load(json_file, object_pairs_hook=OrderedDict)


COLUMNS_DEFINITION = load_definition()
DEFAULT_WEIGHT = 10
DEFAULT_AGGREGATE = 'sum'

SEGMENT_ALL = 'all'
SEGMENT_TOTAL = 't'
SEGMENT_FEMALE = 'f'
SEGMENT_MALE = 'm'
GENDERS = {
    SEGMENT_FEMALE: 'Female',
    SEGMENT_MALE: 'Male',
}

TOPICS = {
    't001': ['segments', 'age_gender', 'families', 'housing'],
    't002': ['education'],
    't003': ['language'],
    't004': ['race_ethnicity'],
    't005': ['nationality', 'migration'],
    't006': ['employment', 'income'],
}


class CensusColumns(ColumnsTask):
    resolution = Parameter()
    topic = Parameter()

    def requires(self):
        return {
            'sections': SectionTags(),
            'subsections': SubsectionTags(),
            'units': UnitTags(),
            'license': LicenseTags(),
            'source': SourceTags(),
            'public': PublicTags()
        }

    def version(self):
        return 1

    def columns(self):
        input_ = self.input()

        license_ca = input_['license']['statcan-license']
        source_ca = input_['source']['statcan-census-2016']
        section = input_['sections']['ca']
        subsections = input_['subsections']
        public = input_['public']['public']

        units = input_['units']

        cols = OrderedDict()

        for key, column in COLUMNS_DEFINITION.items():
            tags = [source_ca, section, public, license_ca, subsections[column['subsection']]]
            tags += [units[column.get('units')]] if column.get('units') is not None else []

            aggregate = column.get('aggregate', DEFAULT_AGGREGATE)
            target = UNIVERSE if aggregate in ('median', 'average') else DENOMINATOR

            cols[key + '_t'] = OBSColumn(
                id=column['id'] + '_t',
                name=column['name'],
                description=column.get('description', ''),
                type='Numeric',
                weight=column.get('weight', DEFAULT_WEIGHT),
                aggregate=aggregate,
                targets={cols[denom + '_t']: target for denom in column['denominators']},
                tags=tags
            )
            if column.get('gender_split', 'no').lower() == 'yes':
                for suffix, gender in GENDERS.items():
                    denominators = ['{}_{}'.format(denom, SEGMENT_TOTAL) for denom in column['denominators']] + \
                                   ['{}_{}'.format(denom, suffix) for denom in column['denominators']]

                    cols['{}_{}'.format(key, suffix)] = OBSColumn(
                        id='{}_{}'.format(column['id'], suffix),
                        name='{} ({})'.format(column['name'], gender),
                        description=column.get('description', ''),
                        type='Numeric',
                        weight=column.get('weight', DEFAULT_WEIGHT),
                        aggregate=aggregate,
                        targets={cols[denom]: target for denom in denominators},
                        tags=tags
                    )

        columnsFilter = ColumnsDeclarations(os.path.join(os.path.dirname(__file__), 'census_columns_filter.json'))
        parameters = '{{"resolution":"{resolution}", "topic":"{topic}"}}'.format(
                        resolution=self.resolution, topic=self.topic)
        cols = columnsFilter.filter_columns(cols, parameters)

        return cols
