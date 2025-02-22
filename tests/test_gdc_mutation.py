import pytest
from oncopacket.cda import GdcService


@pytest.mark.skip('Requires internet connection')
class TestGdcMutationService:

    @pytest.fixture
    def gdc_mutation_service(self) -> GdcService:
        return GdcService()

    def test_fetch_variants(self, gdc_mutation_service: GdcService):
        # TODO: test more
        submitter_id = 'TCGA-DX-A3UA'
        variants = gdc_mutation_service.fetch_variants(submitter_id)
        assert variants
