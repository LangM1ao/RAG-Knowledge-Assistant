from types import SimpleNamespace
from app.services.chunker import chunk_text,chunk_document
from app.services.document_parser import DocumentPage
from app.services.retriever import Retriever


def test_nested_headings_have_paths_and_distinct_leaf_boundaries():
    text='# Manual\n## Storage\n### Quota\nQuota is 8 GB.\n### Recovery\nRetry once.\n'
    chunks=chunk_text(text,'manual.txt',100,10)
    quota=next(c for c in chunks if 'Quota is' in c.text)
    recovery=next(c for c in chunks if 'Retry once' in c.text)
    assert quota.section_path==('Manual','Storage','Quota')
    assert quota.structure_id!=recovery.structure_id
    assert quota.section_title=='Manual' and quota.subsection_title=='Quota'
    assert all(text[c.start_index:c.end_index]==c.text for c in chunks)


def test_dated_project_headings_separate_projects_without_name_rules():
    text=('EXPERIMENTS\nSignal Processing Trial       01/2025 - 02/2025\n'
          '• Uses Fourier transforms.\nSensor Routing Trial       03/2025 - 04/2025\n'
          '• Uses shortest paths.\n')
    chunks=chunk_text(text,'projects.txt',500,50)
    a=next(c for c in chunks if 'Fourier' in c.text)
    b=next(c for c in chunks if 'shortest' in c.text)
    assert 'Sensor Routing' not in a.text and 'Signal Processing' not in b.text
    assert a.structure_id!=b.structure_id
    assert a.subsection_title=='Signal Processing Trial'


def test_repeated_heading_text_has_different_structural_identity():
    chunks=chunk_text('# Manual\n## Setup\nFirst setup.\n## Setup\nSecond setup.','x',100,10)
    items=[c for c in chunks if 'setup.' in c.text]
    assert len(items)==2 and items[0].structure_id!=items[1].structure_id


def test_page_continuation_keeps_true_offsets_and_structural_identity():
    pages=[DocumentPage('# Manual\n## Recovery\nFirst step.\n',1),DocumentPage('Second step.\n',2)]
    chunks=chunk_document(pages,'x.pdf',100,10)
    whole='\n'.join(p.text for p in pages)
    a=next(c for c in chunks if 'First step' in c.text);b=next(c for c in chunks if 'Second step' in c.text)
    assert a.structure_id==b.structure_id and b.page_number==2
    assert all(whole[c.start_index:c.end_index]==c.text for c in chunks)


def test_legacy_or_unknown_structure_is_not_extended():
    anchor={'chunk_id':'old','text':'A','metadata':{'document_id':'d','source_file':'d.txt','section_title':'Same','chunk_index':0}}
    neighbor={'chunk_id':'other','text':'B','metadata':{**anchor['metadata'],'chunk_index':1}}
    class Collection:
        def get(self,**kw):return {'ids':['old','other'],'documents':['A','B'],'metadatas':[anchor['metadata'],neighbor['metadata']]}
    r=Retriever(vector_store=SimpleNamespace(collection=Collection()),alias_records=[])
    assert r.expand_context('A和B是什么？',[anchor])==[anchor]


def test_neighbors_respect_leaf_id_not_only_parent_title():
    def row(i,leaf):return {'chunk_id':str(i),'text':'Evidence '+str(i),'metadata':{'document_id':'d','source_file':'d.txt','section_title':'Manual','chunk_index':i,'structure_id':leaf,'structure_version':2,'structure_reliable':True}}
    rows=[row(0,'a'),row(1,'a'),row(2,'b')]
    class Collection:
        def get(self,**kw):return {'ids':[r['chunk_id'] for r in rows],'documents':[r['text'] for r in rows],'metadatas':[r['metadata'] for r in rows]}
    r=Retriever(vector_store=SimpleNamespace(collection=Collection()),alias_records=[])
    expanded=r.expand_context('分别说明A和B',[rows[1]])
    assert {x['chunk_id'] for x in expanded}=={'0','1'}
