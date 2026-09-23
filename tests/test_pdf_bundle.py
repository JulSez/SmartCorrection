import os
import tempfile
import unittest
from pathlib import Path
from pypdf import PdfReader, PdfWriter
from moteur.pdf_bundle import interleave_packet

class InterleaveTests(unittest.TestCase):
    def test_pairing_preserves_page_order_dimensions_and_selected_copies(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            def pdf(name,widths):
                path=root/name; w=PdfWriter()
                for width in widths: w.add_blank_page(width=width,height=300)
                w.write(str(path)); w.close(); return path
            packet=pdf('packet.pdf',[101,102,103,104])
            first=pdf('first.pdf',[201,202]); second=pdf('second.pdf',[203])
            output=interleave_packet(packet,[(first,[3,1]),(second,[4])],root/'mixed.pdf')
            self.assertEqual([int(p.mediabox.width) for p in PdfReader(output).pages],[103,101,201,202,104,203])
            with self.assertRaisesRegex(ValueError,'Page de copie'):
                interleave_packet(packet,[(first,[5])],root/'invalid.pdf')

    @unittest.skipUnless(os.environ.get('SMARTCORRECTION_TEST_PDF')=='1', 'real PDF integration')
    def test_workflow_generates_both_exports_and_preview(self):
        import test_gui
        from moteur.workflow_v2 import WorkflowApplication
        case=test_gui.GuiWorkflowTests(); case.setUp(); self.addCleanup(case.doCleanups)
        case.pilot()
        case.app=WorkflowApplication(case.root/'db.sqlite',case.root/'data',case.root/'legacy')
        pilot=case.app.generate(case.ident,pdf=True)
        self.assertIn('copies-et-corrections.pdf',pilot['fichiers'])
        self.assertEqual(len(PdfReader(case.app.file('rendu',pilot['id'],'copies-et-corrections.pdf')).pages),10)
        case.exchange('correction',case.corrections(['C006']))
        final=case.app.generate(case.ident,final=True,pdf=True)
        self.assertEqual(len(PdfReader(case.app.file('rendu',final['id'],'corrections.pdf')).pages),7)
        self.assertEqual(len(PdfReader(case.app.file('rendu',final['id'],'copies-et-corrections.pdf')).pages),13)
        self.assertTrue(case.app.state(case.ident)['rendus'][0]['intercale'])
