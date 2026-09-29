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
            self.assertEqual([int(p.mediabox.width) for p in PdfReader(root/'original_first.pdf').pages],[103,101])
            self.assertEqual([int(p.mediabox.width) for p in PdfReader(root/'original_second.pdf').pages],[104])
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

    @unittest.skipUnless(os.environ.get('SMARTCORRECTION_TEST_PDF')=='1', 'real PDF integration')
    def test_late_packet_interleaves_after_calibration_without_reimporting_json(self):
        import base64, io
        from test_workflow_prompts import PromptWorkflowTests
        case=PromptWorkflowTests();case.setUp();self.addCleanup(case.doCleanups)
        case.start()
        first=case.app.generate(case.ident,pdf=True)
        self.assertNotIn('copies-et-corrections.pdf',first['fichiers'])
        stream=io.BytesIO();writer=PdfWriter();writer.add_blank_page(width=333,height=555);writer.write(stream);writer.close()
        case.app.upload(case.ident,'paquet','copies.pdf',base64.b64encode(stream.getvalue()).decode())
        second=case.app.generate(case.ident,pdf=True)
        pdf=PdfReader(case.app.file('rendu',second['id'],'copies-et-corrections.pdf'))
        self.assertEqual(len(pdf.pages),2)
        self.assertEqual(round(float(pdf.pages[0].mediabox.width)),333)
        self.assertTrue(case.app.state(case.ident)['rendus'][0]['intercale'])
