import sys

import utils

# ----------------------------------------------------------------------------------------
def handle_no_space(line, glseqs, qrseqlist):  # NOTE do not, on pain of death, modify <line>
    # if there isn't enough space for dots in the vj line, we add some dashes to everybody so things fit (very rare in heavy chain rearrangements, but pretty common in light chain)
    interior_length = len(line['vd_insertion']) + len(glseqs['d']) + len(line['dj_insertion'])  # length of the portion of the vj line that is normally taken up by dots (and spaces)
    if line['v_3p_del'] + line['j_5p_del'] > interior_length:  # not enough space
        v_3p_del_str = '.' + str(line['v_3p_del']) + '.'
        j_5p_del_str = '.' + str(line['j_5p_del']) + '.'
        extra_space_because_of_fixed_nospace = max(0, interior_length - len(v_3p_del_str + j_5p_del_str))

        gap_insertion_point = len(line['fv_insertion'] + glseqs['v'])
        gaps_to_add = len(v_3p_del_str + j_5p_del_str) - interior_length
        qrseqlist = qrseqlist[:gap_insertion_point] + gaps_to_add * ['-'] + qrseqlist[gap_insertion_point:]
    else:
        v_3p_del_str = '.' * line['v_3p_del']
        j_5p_del_str = '.' * line['j_5p_del']
        gap_insertion_point = None
        gaps_to_add = 0
        extra_space_because_of_fixed_nospace = 0

    return qrseqlist, gap_insertion_point, '-' * gaps_to_add, v_3p_del_str, j_5p_del_str, extra_space_because_of_fixed_nospace

# ----------------------------------------------------------------------------------------
def get_uid_str(line, iseq, seed_uid):
    uid_width = max([len(uid) for uid in line['unique_ids']])
    fstr = '%' + str(uid_width) + 's'
    uidstr = fstr % line['unique_ids'][iseq]
    if seed_uid is not None and line['unique_ids'][iseq] == seed_uid:
        uidstr = utils.color('red', uidstr)
    return uidstr

# ----------------------------------------------------------------------------------------
def indel_shenanigans(outstrs, indels):  # NOTE similar to/overlaps with get_seq_with_indels_reinstated()
    # <outstrs> convention: [indels, d, vj, query]
    def is_qr(index):
        return index == 3
    def use_stars(ifo, index):
        if ifo['type'] == 'insertion': # for insertions, query sequence should *not* have stars
            return not is_qr(index)
        elif ifo['type'] == 'deletion':
            return is_qr(index)
        else:
            assert False
    def reinstate(seq, ifo, istr):
        indelstr = ifo['seqstr']
        if seq[ifo['pos']] not in utils.nukes + utils.ambiguous_bases:  # if this bit of the sequences is spaces, dots, or dashes, then we only want to insert spaces (note that this adds some arbitrariness on boundaries as to who gets the actual inserted string)
            indelstr = ' ' * len(ifo['seqstr'])
        elif use_stars(ifo, istr):
            indelstr = '*' * len(ifo['seqstr'])

        if ifo['type'] == 'deletion':
            return seq[ : ifo['pos']] + indelstr + seq[ifo['pos'] + ifo['len'] : ]
        else:
            return seq[ : ifo['pos']] + indelstr + seq[ifo['pos'] : ]

    for ifo in reversed(indels['indels']):
        outstrs = [reinstate(outstrs[istr], ifo, istr) for istr in range(len(outstrs))]

    return outstrs

# ----------------------------------------------------------------------------------------
def add_colors(outstrs, line, check_line_integrity):  # NOTE do *not* modify <line>
    # <outstrs> convention: [indels, d, vj, query]
    bluechars = utils.ambiguous_bases + ['*', '-']

    if check_line_integrity and len(set([utils.len_excluding_colors(ostr) for ostr in outstrs])) > 1:
        raise Exception('outstrs not all the same length %s' % [utils.len_excluding_colors(ostr) for ostr in outstrs])

    def ismuted(ch1, ch2):
        if ch1 in bluechars or ch2 in bluechars:
            return False
        if ch1 == ch2:
            return False
        return True

    # first color mutated bases and conserved codons in the query sequence
    codon_positions = [p for cpos in line['codon_positions'].values() for p in range(cpos, cpos + 3)]  # *all* the positions in both the codons
    qrseqlist = list(outstrs[-1])
    ipos = 0  # position in real (alphabetical) query sequence
    for inuke in range(len(qrseqlist)):
        if '*' in ''.join([outstrs[i][inuke] for i in range(3)]):  # if any of the germline lines have a star at this position, i.e. if we're in an shm insertion (if the query line has a star, it's an shm deletion, i.e. the star's position was actually there as a base in the hmm)
            continue
        glchars = [ostr[inuke] for ostr in outstrs[:3] if ostr[inuke] in utils.alphabet]
        if len(glchars) == 0:  # everybody's spaces, dashes, or dots (I think those are the only possibilities...)
            continue
        if len(glchars) > 1:
            raise Exception('more than one germline line has an alphabet character at %d: %s' % (inuke, glchars))
        if ismuted(qrseqlist[inuke], glchars[0]):
            qrseqlist[inuke] = utils.color('red', qrseqlist[inuke])
        if ipos in codon_positions:
            qrseqlist[inuke] = utils.color('reverse_video', qrseqlist[inuke])
        ipos += 1

    outstrs = [outstrs[i] for i in range(3)] + [''.join(qrseqlist)]

    # then color the blues in everybody
    for istr in range(len(outstrs)):
        if len(filter((bluechars).__contains__, outstrs[istr])) == 0:
            continue
        oslist = list(outstrs[istr])
        oslist = [utils.color('light_blue', ochar) if ochar in bluechars else ochar for ochar in oslist]
        outstrs[istr] = ''.join(oslist)

    return outstrs
