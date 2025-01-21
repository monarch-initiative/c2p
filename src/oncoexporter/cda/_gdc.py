import json
import logging
import typing

import pandas as pd
import phenopackets as pp
import requests
from io import StringIO


class GdcService:
    """
    `GdcService` queries Genomic Data Commons REST endpoints to fetch items not available in CDA
    for a CDA subject:
        variants
        vital status
        stage

    Changed the name from GdcMutationService since we are using it to get things in addition to variants
    """

    def __init__(
            self,
            page_size=100,
            page=1,
            timeout=10,
    ):
        self._logger = logging.getLogger(__name__)
        self._variants_url = 'https://api.gdc.cancer.gov/ssms'
        self._survival_url = 'https://api.gdc.cancer.gov/analysis/survival'
        self._cases_url = 'https://api.gdc.cancer.gov/cases'
        self._page_size = page_size
        self._page = page
        self._timeout = timeout
        self._variant_fields = ','.join((
            # "mutation_type",
            # "mutation_subtype",
            "ncbi_build",
            "chromosome",
            "start_position",
            # "end_position",
            "reference_allele",
            "tumor_allele",
            # "genomic_dna_change",
            # "end_position",
            # "gene_aa_change",
            "consequence.transcript.gene.gene_id",
            "consequence.transcript.gene.symbol",
            "consequence.transcript.transcript_id",
            "consequence.transcript.annotation.hgvsc",
        ))
        self._case_fields = ','.join((
            "demographic.vital_status",
            "diagnoses.ajcc_pathologic_stage",
        ))

    def _fetch_data_from_gdc(self, url: str, subject_id: str, fields: typing.List[str]=None) -> typing.Any:
        params = self._prepare_query_params(subject_id, fields)
        response = requests.get(url, params=params, timeout=self._timeout)
        #response_b = requests.post(url, headers = {"Content-Type": "application/json"}, json = params)

        if response.status_code == 200:
            data = response.json()
            return data
        else:
            raise ValueError(f'Failed to fetch data from {url} due to {response.status_code}: {response.reason}')

    def _prepare_query_params(self, subject_ids: typing.List, fields: typing.List[str]=None) -> typing.Dict:

        filters = {
            "op": "in",
            "content": {
                "field": "cases.submitter_id",
                "value": [subject_ids]
            }
        }
        # filters = {"op":"and","content":[{"op":"in","content":{"field":"submitter_id","value":subj}}]}

        return {
            "fields": fields,
            "filters": json.dumps(filters),
            "format": "JSON",
            "size": self._page_size,
        }

    def fetch_variants(self, subject_id: str) -> typing.Sequence[pp.VariantInterpretation]:
        variants = self._fetch_data_from_gdc(self._variants_url, subject_id, self._variant_fields)
        # need to do a POST, GET takes too long...

        mutations = variants.get("data", {}).get("hits", [])

        mutation_details = []
        for mutation in mutations:
            print(mutation)
            vi = self._map_mutation_to_variant_interpretation(mutation)
            mutation_details.append(vi)

        return mutation_details

    def fetch_vital_status(self, subject_id: str) -> pp.VitalStatus:
        '''
        Need to make sure we are getting demographics.time_to_last_follow_up and demographics.time_to_last_known_disease_status for
        survival analysis of patients who have not died
        
        
        '''
        survival_data = self._fetch_data_from_gdc(self._survival_url, subject_id)
        vital_status_data = self._fetch_data_from_gdc(self._cases_url, subject_id, self._case_fields)

        survival_time = None
        vital_status = None

        # need to get 'censored' field as well? And survival estimate?
        survival_results = survival_data.get("results", [])
        if survival_results:
            donors = survival_results[0].get("donors", [])
            if donors:
                survival_time = donors[0].get("time")

        vital_status_hits = vital_status_data.get("data", {}).get("hits", [])
        if vital_status_hits:
            demographic = vital_status_hits[0].get("demographic", {})
            vital_status = demographic.get("vital_status")

        vital_status_obj = pp.VitalStatus()
        vital_status_obj.survival_time_in_days = int(survival_time) if survival_time is not None else 0
        if vital_status == "Dead":
            vital_status_obj.status = pp.VitalStatus.Status.DECEASED
        elif vital_status == "Alive":
            vital_status_obj.status = pp.VitalStatus.Status.ALIVE
        else:
            vital_status_obj.status = pp.VitalStatus.Status.UNKNOWN_STATUS

        return vital_status_obj

    def fetch_stage(self, subject_id: str) -> str:

        stage = 'Unknown'
        stage_data = self._fetch_data_from_gdc(self._cases_url, subject_id, self._case_fields)

        stage_hits = stage_data.get("data", {}).get("hits", [])
        # [{'id': 'bdd09566-f2ba-4771-82eb-9c30563dc669', 'diagnoses': [{'ajcc_pathologic_stage': 'Stage I'}], 'demographic': {'vital_status': 'Alive'}}]
        # gdc_stage: Stage I
        if stage_hits:
            diagnoses = stage_hits[0].get("diagnoses", {})
            if diagnoses:
                stage = diagnoses[0].get("ajcc_pathologic_stage")
            #else:
                #print("No diagnoses...")
        #else:
            #print("No stage_hits...", stage_data)

        return stage

    def fetch_stage_dict(self) -> dict:
        '''
         Get df from GDC API with stages for input list of subject IDs using POST instead of GET
          - speeds up creating of phenopackets
          - returns a dictionary of subject ID -> stage
          
        Note: diagnoses.tumor_stage is empty, with 4 other options available
            - not clear if they conflict with each other
            - ajcc_pathologic_stage has the highest number so we use that initially 
        '''
        
        fields = [
             "submitter_id",
             "cases.submitter_id",
             "diagnoses.ajcc_pathologic_stage" # one of 4 options (ajcc_clinical, ann_arbor_pathologic, ann_arbor_clinical)
         ]
        fields = ",".join(fields)

        # A POST is used, so the filter parameters can be passed directly as a Dict object.
        params = {
             "fields": fields,
             "format": "TSV",
             "size": "50000"
             }

        # The parameters are passed to 'json' rather than 'params' in this case
        response = requests.post(self._cases_url, headers = {"Content-Type": "application/json"}, json = params)
        stage_df = pd.read_csv(StringIO(response.content.decode("utf-8")), sep='\t')
        stage_df.columns = ['ajcc0', 'ajcc1', 'ajcc2','id','submitter_id']
        #stage_df.head()
        #stage_df.shape
        stage_dict = dict(zip(stage_df.submitter_id, stage_df.ajcc0))
        
        return stage_dict
    
    #def fetch_stage_df(self, subj_id_list) -> pd.DataFrame:
    #    '''
    #    Get df from GDC API with stages for input list of subject IDs
    #    '''
    #    stage_data = self._fetch_data_from_gdc(self._cases_url, subj_id_list, self._case_fields)

    #    return stage_data
    def _map_mutation_to_variant_interpretation(self, mutation) -> pp.VariantInterpretation:
        vcf_record = self._parse_vcf_record(mutation)

        vd = pp.VariationDescriptor()
        vd.id = mutation['id']

        if vcf_record is not None:
            vd.vcf_record.CopyFrom(vcf_record)

        # TODO: 't_depth', 't_ref_count', 't_alt_count', 'n_depth', 'n_ref_count', 'n_alt_count'
        # TODO: mutation status

        for csq in mutation['consequence']:
          
            (expression, gene_descriptor) = (
                GdcMutationService._map_consequence_to_expression_and_gene_descriptor(csq))

            if expression is not None:
                vd.expressions.append(expression)
            if gene_descriptor is not None:
                vd.gene_context.CopyFrom(gene_descriptor)

        vd.molecule_context = pp.MoleculeContext.genomic

        vi = pp.VariantInterpretation()
        vi.variation_descriptor.CopyFrom(vd)
        return vi

    def _parse_vcf_record(self, mutation) -> typing.Optional[pp.VcfRecord]:
        if mutation['reference_allele'] == '-' or mutation['tumor_allele'] == '-':
            self._logger.debug(
                'Cannot create a VCF record due to missing bases in the reference_allele/tumor_allele alleles: %s',
                mutation)
            return None

        vcf_record = pp.VcfRecord()

        vcf_record.genome_assembly = mutation['ncbi_build']
        vcf_record.chrom = mutation['chromosome']
        vcf_record.id = mutation['id']
        vcf_record.pos = mutation['start_position']
        vcf_record.ref = mutation['reference_allele']
        vcf_record.alt = mutation['tumor_allele']

        return vcf_record

    @staticmethod
    def _map_consequence_to_expression_and_gene_descriptor(csq) -> (typing.Optional[pp.Expression],
                                                                    typing.Optional[pp.GeneDescriptor]):
        tx = csq['transcript']
        print(tx)
        
        #     "consequence.transcript.gene.gene_id",
        #    "consequence.transcript.gene.symbol",
        
        expression = pp.Expression()
        expression.syntax = 'hgvs.c'
        tx_id = tx['transcript_id']
        ann = tx['annotation']['hgvsc']
        expression.value = f'{tx_id}:{ann}'

        gene_context = pp.GeneDescriptor()
        gene_context.value_id = tx['gene']['gene_id']
        gene_context.symbol = tx['gene']['symbol']

        return (expression, gene_context)

