#!/usr/bin/env python
import argparse
import contextlib
import csv
import logging
import functools
import shutil
import subprocess
import tempfile

from pkg_resources import resource_stream
import pysam

log = logging.getLogger('vdjalign')

from . import util
from imgt import igh

BWA_OPTS = ['-k', '6', '-O', '10', '-L', '0', '-v', '2', '-a', '-T', '10']

@contextlib.contextmanager
def bwa_index_of_package_imgt_fasta(file_name):
    with util.tempdir(prefix='bwa-') as td, \
         resource_stream('vdjalign.imgt.data', file_name) as in_fasta:
        with open(td(file_name), 'w') as fp:
            shutil.copyfileobj(in_fasta, fp)
        cmd = ['bwa', 'index', file_name]
        log.info('Running "%s" in %s', ' '.join(cmd), td())
        subprocess.check_call(cmd, cwd=td())
        yield td(file_name)

def identify_frame_cdr3(input_bam):
    cysteine_map = igh.cysteine_map()
    tid_map = {input_bam.getrname(tid): tid for tid in xrange(input_bam.nreferences)}
    tid_cysteine_map = {tid_map[k]: v for k, v in cysteine_map.iteritems() if k in tid_map}
    for read in input_bam:
        if read.is_unmapped:
            yield read
            continue

        cysteine_position = tid_cysteine_map[read.tid]

        if read.aend < cysteine_position + 2:
            #if not read.is_secondary:
                #log.warn('Alignment does not cover Cysteine: (%d < %d)',
                        #read.aend, cysteine_position + 2)
            yield read
            continue

        cdr3_start = cysteine_position - read.pos + read.qstart
        read.tags = read.tags + [('cs', cdr3_start), ('fr', (cdr3_start % 3) + 1)]
        yield read

def identify_cdr3_end(j_bam, v_metadata):
    for read in j_bam:
        if read.is_unmapped:
            yield read
            continue
        meta = v_metadata[read.qname]
        orig_frame = meta['frame']
        if not read.is_secondary and orig_frame:
            orig_qend = meta['qend']
            new_start_frame = (read.qstart + orig_qend) % 3
            new_frame = ((orig_frame - 1) + 3 - new_start_frame) % 3 + 1
            new_tags = [('fr', new_frame)]

            # Find CDR3 end
            s = read.query
            assert s is not None
            for i in xrange(new_frame - 1, len(s), 3):
                if s[i:i+3] == 'TGG':
                    new_tags.append(('ce', read.qstart + orig_qend + i + 3))
            read.tags = read.tags + new_tags
        yield read

def bwa_to_bam(index_path, sequence_iter, bam_dest, bwa_opts=None, sam_opts=None, alg='mem'):
    cmd1 = ['bwa', alg, index_path, '-'] + (bwa_opts or [])
    cmd2 = ['samtools', 'view', '-Su', '-o', bam_dest, '-'] + (sam_opts or [])
    log.info('BWA: %s | %s', ' '.join(cmd1), ' '.join(cmd2))
    p1 = subprocess.Popen(cmd1, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    p2 = subprocess.Popen(cmd2, stdin=p1.stdout)

    with p1.stdin as fp:
        for name, seq in sequence_iter:
            fp.write('>{0}\n{1}\n'.format(name, seq))
    exit_code2 = p2.wait()

    if exit_code2:
        raise subprocess.CalledProcessError(exit_code2, cmd2)

    exit_code1 = p1.wait()
    if exit_code1:
        raise subprocess.CalledProcessError(exit_code1, cmd1)

def align_v(v_index_path, sequence_iter, bam_dest, threads=1):
    opts = BWA_OPTS[:]
    if threads > 1:
        opts.extend(('-t', str(threads)))
    return bwa_to_bam(v_index_path, sequence_iter, bam_dest, bwa_opts=opts)

def extract_unaligned_tail(bamfile):
    """
    Given a bamfile, yield (name, seq) tuples where seq is the clipped section
    of `seq` on the 3' end.
    """
    #CLIP = (4, 5) # S, H
    for read in bamfile:
        if read.is_secondary or read.is_unmapped:
            continue

        unaligned_tail = read.seq[read.qend:]
        if unaligned_tail:
            yield read.qname, unaligned_tail

def align_j(j_index_path, v_bam, bam_dest, threads=1):
    opts = BWA_OPTS[:]
    if threads > 1:
        opts.extend(('-t', str(threads)))
    sequences = extract_unaligned_tail(v_bam)
    return bwa_to_bam(j_index_path, sequences, bam_dest, bwa_opts=opts)

def main():
    p = argparse.ArgumentParser()
    p.add_argument('csv_file', type=util.opener('rU'))
    p.add_argument('-t', '--tab-delimited', action='store_const',
            dest='delimiter', const='\t', default=',')
    p.add_argument('-s', '--sequence-column', default='nucleotide',
            help="""Name of column with nucleotide sequence""")
    p.add_argument('-j', '--threads', default=1, type=int, help="""Number of
            threads for BWA [default: %(default)d]""")
    p.add_argument('v_bamfile')
    p.add_argument('j_bamfile')
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO)

    indexed = bwa_index_of_package_imgt_fasta
    ntf = functools.partial(tempfile.NamedTemporaryFile, suffix='.bam')
    closing = contextlib.closing

    with indexed('ighv.fasta') as v_index, \
         indexed('ighj.fasta') as j_index, \
         a.csv_file as ifp, \
         ntf(prefix='v_alignments-') as v_tf, \
         ntf(prefix='j_alignments-') as j_tf:

        csv_lines = (i for i in ifp if not i.startswith('#'))
        r = csv.DictReader(csv_lines, delimiter=a.delimiter)
        sequences = (('{0}'.format(i), row[a.sequence_column])
                     for i, row in enumerate(r))

        res_map = {}
        align_v(v_index, sequences, v_tf.name, threads=a.threads)
        with closing(pysam.Samfile(v_tf.name, 'rb')) as v_tmp_bam, \
             closing(pysam.Samfile(a.v_bamfile, 'wb', template=v_tmp_bam)) as v_bam:
            log.info('Identifying frame and CDR3 start')
            reads = identify_frame_cdr3(v_tmp_bam)
            for read in reads:
                if not read.is_secondary and not read.is_unmapped:
                    fr = None
                    try:
                        fr = read.opt('fr')
                    except KeyError:
                        pass
                    res_map[read.qname] = {'qend': read.qend, 'frame': fr, 'qlen': read.qlen}
                v_bam.write(read)

        with closing(pysam.Samfile(a.v_bamfile, 'rb')) as v_bam:
            log.info('Aligning J-region')
            align_j(j_index, v_bam, j_tf.name, threads=a.threads)
        with closing(pysam.Samfile(j_tf.name, 'rb')) as j_tmp_bam, \
             closing(pysam.Samfile(a.j_bamfile, 'wb', template=j_tmp_bam)) as j_bam:
            log.info('Identifying CDR3 end')
            reads = identify_cdr3_end(j_tmp_bam, res_map)
            for read in reads:
                j_bam.write(read)

if __name__ == '__main__':
    main()
