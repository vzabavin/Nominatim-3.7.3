# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of Nominatim. (https://nominatim.org)
#
# Copyright (C) 2023 by the Nominatim developer community.
# For a full list of authors see the git log.
"""
Create query interpretations where each vertice in the query is assigned
a specific function (expressed as a token type).
"""
from typing import Optional, List, Iterator
import dataclasses

import nominatim.api.search.query as qmod
from nominatim.api.logging import log

# pylint: disable=too-many-return-statements,too-many-branches

@dataclasses.dataclass
class TypedRange:
    """ A token range for a specific type of tokens.
    """
    ttype: qmod.TokenType
    trange: qmod.TokenRange


PENALTY_TOKENCHANGE = {
    qmod.BreakType.START: 0.0,
    qmod.BreakType.END: 0.0,
    qmod.BreakType.PHRASE: 0.0,
    qmod.BreakType.WORD: 0.1,
    qmod.BreakType.PART: 0.2,
    qmod.BreakType.TOKEN: 0.4
}

TypedRangeSeq = List[TypedRange]

@dataclasses.dataclass
class TokenAssignment: # pylint: disable=too-many-instance-attributes
    """ Representation of a possible assignment of token types
        to the tokens in a tokenized query.
    """
    penalty: float = 0.0
    name: Optional[qmod.TokenRange] = None
    address: List[qmod.TokenRange] = dataclasses.field(default_factory=list)
    housenumber: Optional[qmod.TokenRange] = None
    postcode: Optional[qmod.TokenRange] = None
    country: Optional[qmod.TokenRange] = None
    category: Optional[qmod.TokenRange] = None
    qualifier: Optional[qmod.TokenRange] = None


    @staticmethod
    def from_ranges(ranges: TypedRangeSeq) -> 'TokenAssignment':
        """ Create a new token assignment from a sequence of typed spans.
        """
        out = TokenAssignment()
        for token in ranges:
            if token.ttype == qmod.TokenType.PARTIAL:
                out.address.append(token.trange)
            elif token.ttype == qmod.TokenType.HOUSENUMBER:
                out.housenumber = token.trange
            elif token.ttype == qmod.TokenType.POSTCODE:
                out.postcode = token.trange
            elif token.ttype == qmod.TokenType.COUNTRY:
                out.country = token.trange
            elif token.ttype == qmod.TokenType.CATEGORY:
                out.category = token.trange
            elif token.ttype == qmod.TokenType.QUALIFIER:
                out.qualifier = token.trange
        return out


class _TokenSequence:
    """ Working state used to put together the token assignements.

        Represents an intermediate state while traversing the tokenized
        query.
    """
    def __init__(self, seq: TypedRangeSeq,
                 direction: int = 0, penalty: float = 0.0) -> None:
        self.seq = seq
        self.direction = direction
        self.penalty = penalty


    def __str__(self) -> str:
        seq = ''.join(f'[{r.trange.start} - {r.trange.end}: {r.ttype.name}]' for r in self.seq)
        return f'{seq} (dir: {self.direction}, penalty: {self.penalty})'


    @property
    def end_pos(self) -> int:
        """ Return the index of the global end of the current sequence.
        """
        return self.seq[-1].trange.end if self.seq else 0


    def has_types(self, *ttypes: qmod.TokenType) -> bool:
        """ Check if the current sequence contains any typed ranges of
            the given types.
        """
        return any(s.ttype in ttypes for s in self.seq)


    def is_final(self) -> bool:
        """ Return true when the sequence cannot be extended by any
            form of token anymore.
        """
        # Country and category must be the final term for left-to-right
        return len(self.seq) > 1 and \
               self.seq[-1].ttype in (qmod.TokenType.COUNTRY, qmod.TokenType.CATEGORY)


    def appendable(self, ttype: qmod.TokenType) -> Optional[int]:
        """ Check if the give token type is appendable to the existing sequence.

            Returns None if the token type is not appendable, otherwise the
            new direction of the sequence after adding such a type. The
            token is not added.
        """
        if ttype == qmod.TokenType.WORD:
            return None

        if not self.seq:
            # Append unconditionally to the empty list
            if ttype == qmod.TokenType.COUNTRY:
                return -1
            if ttype in (qmod.TokenType.HOUSENUMBER, qmod.TokenType.QUALIFIER):
                return 1
            return self.direction

        # Name tokens are always acceptable and don't change direction
        if ttype == qmod.TokenType.PARTIAL:
            return self.direction

        # Other tokens may only appear once
        if self.has_types(ttype):
            return None

        if ttype == qmod.TokenType.HOUSENUMBER:
            if self.direction == 1:
                if len(self.seq) == 1 and self.seq[0].ttype == qmod.TokenType.QUALIFIER:
                    return None
                if len(self.seq) > 2 \
                   or self.has_types(qmod.TokenType.POSTCODE, qmod.TokenType.COUNTRY):
                    return None # direction left-to-right: housenumber must come before anything
            elif self.direction == -1 \
                 or self.has_types(qmod.TokenType.POSTCODE, qmod.TokenType.COUNTRY):
                return -1 # force direction right-to-left if after other terms

            return self.direction

        if ttype == qmod.TokenType.POSTCODE:
            if self.direction == -1:
                if self.has_types(qmod.TokenType.HOUSENUMBER, qmod.TokenType.QUALIFIER):
                    return None
                return -1
            if self.direction == 1:
                return None if self.has_types(qmod.TokenType.COUNTRY) else 1
            if self.has_types(qmod.TokenType.HOUSENUMBER, qmod.TokenType.QUALIFIER):
                return 1
            return self.direction

        if ttype == qmod.TokenType.COUNTRY:
            return None if self.direction == -1 else 1

        if ttype == qmod.TokenType.CATEGORY:
            return self.direction

        if ttype == qmod.TokenType.QUALIFIER:
            if self.direction == 1:
                if (len(self.seq) == 1
                    and self.seq[0].ttype in (qmod.TokenType.PARTIAL, qmod.TokenType.CATEGORY)) \
                   or (len(self.seq) == 2
                       and self.seq[0].ttype == qmod.TokenType.CATEGORY
                       and self.seq[1].ttype == qmod.TokenType.PARTIAL):
                    return 1
                return None
            if self.direction == -1:
                return -1

            tempseq = self.seq[1:] if self.seq[0].ttype == qmod.TokenType.CATEGORY else self.seq
            if len(tempseq) == 0:
                return 1
            if len(tempseq) == 1 and self.seq[0].ttype == qmod.TokenType.HOUSENUMBER:
                return None
            if len(tempseq) > 1 or self.has_types(qmod.TokenType.POSTCODE, qmod.TokenType.COUNTRY):
                return -1
            return 0

        return None


    def advance(self, ttype: qmod.TokenType, end_pos: int,
                btype: qmod.BreakType) -> Optional['_TokenSequence']:
        """ Return a new token sequence state with the given token type
            extended.
        """
        newdir = self.appendable(ttype)
        if newdir is None:
            return None

        if not self.seq:
            newseq = [TypedRange(ttype, qmod.TokenRange(0, end_pos))]
            new_penalty = 0.0
        else:
            last = self.seq[-1]
            if btype != qmod.BreakType.PHRASE and last.ttype == ttype:
                # extend the existing range
                newseq = self.seq[:-1] + [TypedRange(ttype, last.trange.replace_end(end_pos))]
                new_penalty = 0.0
            else:
                # start a new range
                newseq = list(self.seq) + [TypedRange(ttype,
                                                      qmod.TokenRange(last.trange.end, end_pos))]
                new_penalty = PENALTY_TOKENCHANGE[btype]

        return _TokenSequence(newseq, newdir, self.penalty + new_penalty)


    def _adapt_penalty_from_priors(self, priors: int, new_dir: int) -> bool:
        if priors == 2:
            self.penalty += 1.0
        elif priors > 2:
            if self.direction == 0:
                self.direction = new_dir
            else:
                return False

        return True


    def recheck_sequence(self) -> bool:
        """ Check that the sequence is a fully valid token assignment
            and addapt direction and penalties further if necessary.

            This function catches some impossible assignments that need
            forward context and can therefore not be exluded when building
            the assignment.
        """
        # housenumbers may not be further than 2 words from the beginning.
        # If there are two words in front, give it a penalty.
        hnrpos = next((i for i, tr in enumerate(self.seq)
                       if tr.ttype == qmod.TokenType.HOUSENUMBER),
                      None)
        if hnrpos is not None:
            if self.direction != -1:
                priors = sum(1 for t in self.seq[:hnrpos] if t.ttype == qmod.TokenType.PARTIAL)
                if not self._adapt_penalty_from_priors(priors, -1):
                    return False
            if self.direction != 1:
                priors = sum(1 for t in self.seq[hnrpos+1:] if t.ttype == qmod.TokenType.PARTIAL)
                if not self._adapt_penalty_from_priors(priors, 1):
                    return False

        return True


    def get_assignments(self, query: qmod.QueryStruct) -> Iterator[TokenAssignment]:
        """ Yield possible assignments for the current sequence.

            This function splits up general name assignments into name
            and address and yields all possible variants of that.
        """
        base = TokenAssignment.from_ranges(self.seq)

        # Postcode search (postcode-only search is covered in next case)
        if base.postcode is not None and base.address:
            if (base.postcode.start == 0 and self.direction != -1)\
               or (base.postcode.end == query.num_token_slots() and self.direction != 1):
                log().comment('postcode search')
                # <address>,<postcode> should give preference to address search
                if base.postcode.start == 0:
                    penalty = self.penalty
                else:
                    penalty = self.penalty + 0.1
                yield dataclasses.replace(base, penalty=penalty)

        # Postcode or country-only search
        if not base.address:
            if not base.housenumber and (base.postcode or base.country or base.category):
                log().comment('postcode/country search')
                yield dataclasses.replace(base, penalty=self.penalty)
        else:
            # <postcode>,<address> should give preference to postcode search
            if base.postcode and base.postcode.start == 0:
                self.penalty += 0.1
            # Use entire first word as name
            if self.direction != -1:
                log().comment('first word = name')
                yield dataclasses.replace(base, name=base.address[0],
                                          penalty=self.penalty,
                                          address=base.address[1:])

            # Use entire last word as name
            if self.direction == -1 or (self.direction == 0 and len(base.address) > 1):
                log().comment('last word = name')
                yield dataclasses.replace(base, name=base.address[-1],
                                          penalty=self.penalty,
                                          address=base.address[:-1])

            # variant for special housenumber searches
            if base.housenumber:
                yield dataclasses.replace(base, penalty=self.penalty)

            # Use beginning of first word as name
            if self.direction != -1:
                first = base.address[0]
                if (not base.housenumber or first.end >= base.housenumber.start)\
                   and (not base.qualifier or first.start >= base.qualifier.end):
                    base_penalty = self.penalty
                    if (base.housenumber and base.housenumber.start > first.start) \
                       or len(query.source) > 1:
                        base_penalty += 0.25
                    for i in range(first.start + 1, first.end):
                        name, addr = first.split(i)
                        penalty = base_penalty + PENALTY_TOKENCHANGE[query.nodes[i].btype]
                        log().comment(f'split first word = name ({i - first.start})')
                        yield dataclasses.replace(base, name=name, penalty=penalty,
                                                  address=[addr] + base.address[1:])

            # Use end of last word as name
            if self.direction != 1:
                last = base.address[-1]
                if (not base.housenumber or last.start <= base.housenumber.end)\
                   and (not base.qualifier or last.end <= base.qualifier.start):
                    base_penalty = self.penalty
                    if base.housenumber and base.housenumber.start < last.start:
                        base_penalty += 0.4
                    if len(query.source) > 1:
                        base_penalty += 0.25
                    for i in range(last.start + 1, last.end):
                        addr, name = last.split(i)
                        penalty = base_penalty + PENALTY_TOKENCHANGE[query.nodes[i].btype]
                        log().comment(f'split last word = name ({i - last.start})')
                        yield dataclasses.replace(base, name=name, penalty=penalty,
                                                  address=base.address[:-1] + [addr])



def yield_token_assignments(query: qmod.QueryStruct) -> Iterator[TokenAssignment]:
    """ Return possible word type assignments to word positions.

        The assignments are computed from the concrete tokens listed
        in the tokenized query.

        The result includes the penalty for transitions from one word type to
        another. It does not include penalties for transitions within a
        type.
    """
    todo = [_TokenSequence([], direction=0 if query.source[0].ptype == qmod.PhraseType.NONE else 1)]

    while todo:
        state = todo.pop()
        node = query.nodes[state.end_pos]

        for tlist in node.starting:
            newstate = state.advance(tlist.ttype, tlist.end, node.btype)
            if newstate is not None:
                if newstate.end_pos == query.num_token_slots():
                    if newstate.recheck_sequence():
                        log().var_dump('Assignment', newstate)
                        yield from newstate.get_assignments(query)
                elif not newstate.is_final():
                    todo.append(newstate)
