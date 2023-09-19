
from unittest import TestCase
from oncopacket.model import OpIndividual

class OpIndividualTestCase(TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        data = ['CGCI.HTMCP-03-06-02007',
                "[{'system': 'GDC', 'field_name': 'case.submitter_id', 'value': 'HTMCP-03-06-02007'}]",
                'Homo sapiens',
                'female',
                'black or african american',
                'not reported',
                '-15987.0',
                "['CGCI-HTMCP-CC']",
                "Alive",
                "NaN",
                "None"]
        column_names = ['subject_id', 'subject_identifier', 'species', 'sex', 'race',
                        'ethnicity', 'days_to_birth', 'subject_associated_project',
                        'vital_status', 'days_to_death', 'cause_of_death']
        cls._series = pd.Series(data, index=column_names)

    def test_creation(self):
        ifact = Op()
        self.assertIsNotNone(ifact)
        ga4gh_indi = ifact.from_cancer_data_aggregator(self._series)
        self.assertIsNotNone(ga4gh_indi)

    def test_id(self):
        ifact = IndividualFactory()
        ga4gh_indi = ifact.from_cancer_data_aggregator(self._series)
        expected_id = 'CGCI.HTMCP-03-06-02007'
        self.assertEquals(expected_id, ga4gh_indi.id)

    def test_iso_age(self):
        ifact = IndividualFactory()
        ga4gh_indi = ifact.from_cancer_data_aggregator(self._series)
        expected_iso = 'P43Y43M6D'
        calculated_iso = ga4gh_indi.time_at_last_encounter.age.iso8601duration
        self.assertEquals(expected_iso, calculated_iso)

