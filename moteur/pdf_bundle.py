"""Pair original copy pages with their generated correction sheets."""
from pathlib import Path


def interleave_packet(packet, entries, output):
    from pypdf import PdfReader, PdfWriter
    reader = PdfReader(str(packet))
    writer = PdfWriter()
    try:
        for correction, pages in entries:
            split = PdfWriter()
            for page in pages:
                if type(page) is not int or not 1 <= page <= len(reader.pages):
                    raise ValueError(f'Page de copie absente du PDF : {page}')
                split.add_page(reader.pages[page-1])
                writer.add_page(reader.pages[page-1])
            try:
                if pages:
                    split.write(str(Path(output).parent/('original_'+Path(correction).name)))
            finally:
                split.close()
            writer.append(str(correction))
        writer.write(str(output))
    finally:
        writer.close()
    return Path(output)
