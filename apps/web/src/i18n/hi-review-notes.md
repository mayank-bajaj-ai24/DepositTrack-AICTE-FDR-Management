# Hindi translation: notes for the reviewer

`hi.json` was written by Claude and still needs a fluent reviewer (`pending.md`, item 9). These
notes come from a machine read of all 286 strings on 26 Oct 2026. They make no change to
`hi.json`; each line is a question for the reviewer to accept or reject.

**Checked automatically:** every key in `en.json` is present in `hi.json` and vice versa, every
`{placeholder}` is kept, and the only untranslated strings are the brand name and `{institution}`.

## Worth a decision

| Key(s) | English | Current Hindi | Question for the reviewer |
| --- | --- | --- | --- |
| `nav.submit`, `submit.title`, `common.submit`, `state.submitted`, `submit.done`, `app.tagline` | Submit / Submitted | जमा करें / जमा किया गया | **जमा also means "deposit"**, so "एफडीआर जमा करें" reads as "deposit an FDR" and the tagline's "जमा करने से" is ambiguous. Use प्रस्तुत करें / प्रस्तुत किया गया for submit? |
| `nav.queue`, `state.scrutiny`, `queue.*`, `detail.observations` | Scrutiny | जाँच | The official term for scrutiny is संवीक्षा. Keep the everyday जाँच, or use संवीक्षा? |
| `state.discrepancy` | Query raised | प्रश्न उठाया गया | Office usage for a query on a file is usually पृच्छा or आपत्ति. |
| `nav.cases`, `cases.type.release`, `state.releasing`, `state.released`, `event.release.*` | Release | रिलीज़ | A transliteration. निर्मुक्ति (release of a security deposit) is the formal term. Is the transliteration clearer for users? |
| `cases.type.discharge` | Discharge | मुक्ति | Banking Hindi uses उन्मोचन for discharge. |
| `cases.type.refund` | Refund | वापसी | धनवापसी is more specific. |
| `nav.instruments`, `list.*`, `event.instrument.created` | Instrument(s) | लिखत | Correct banking term, but institution users may not know it. Use लिखत (एफडीआर आदि) once on the list page? |
| `flag.duplicate_pledge` | Same FDR pledged twice | एक ही एफडीआर दो बार गिरवी | Incomplete without a verb: एक ही एफडीआर दो बार गिरवी रखा गया. |
| `flag.invalid_ifsc` | IFSC format | आईएफएससी का प्रारूप | The English is terse too. Use "आईएफएससी का प्रारूप गलत" (and "Invalid IFSC format")? |
| `event.instrument.state_changed` | State changed | स्थिति बदली | स्थिति बदली गई matches the other event strings (passive, completed). |
| `col.flags` | Flags | विसंगतियाँ | Means "discrepancies", which is the intent. Fine if a forgery signal also counts as a discrepancy. |

## Read and found fine

Navigation, auth, banners, the Trust Ladder levels, field names (एफडीआर संख्या, परिपक्वता तिथि,
ग्रहणाधिकार का पाठ, लाभार्थी), severities, audit (लेखा-परीक्षा, हैश शृंखला अक्षुण्ण), reports,
admin and notification strings.
