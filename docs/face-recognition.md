# Face recognition

Face recognition lets bindings react to *who* is in front of the camera: greet someone,
notify you when a stranger shows up, or make gestures work only for registered people.

## How it works

1. **Detection.** OpenCV's YuNet model finds faces and five landmarks (eyes, nose, mouth
   corners) in a 640 px wide copy of the frame.
2. **Embedding.** Each face is aligned with those landmarks and SFace turns it into 128
   numbers. Pictures of the same person give embeddings that point in a similar direction.
3. **Matching.** The embedding is compared with every stored sample using cosine
   similarity. The best person wins if the similarity is above the *Strictness* threshold;
   otherwise the face is *unknown*.
4. **Voting.** Faces are tracked across frames, and a decision needs several matching votes
   (*Confirmation*: instant, normal or safe). Small or low-confidence detections do not
   vote, so someone far from the camera is not suddenly marked unknown.

No model is trained on your data. Adding a person only stores their embeddings.

## Registering someone

*Faces > People > +*, then give them a name and:

- **Capture with the camera**: look at the camera and turn your head slowly for 8 seconds.
  Up to 15 samples are taken from good frames.
- **Add photos**: pick photos where the face is clear. If there are several faces, the
  largest one is used.

Samples that are almost identical to an existing one are skipped. Ten to twenty samples
with different angles and lighting work best; the list shows a warning for fewer than five.

## Tuning

- **Strictness** (0.25 to 0.70, default 0.40). Raise it if two people get confused, lower
  it if you are often *unknown* in poor light.
- **Confirmation**. *Instant* decides on the first good frame (about a tenth of a second)
  but one bad frame can mislead it. *Safe* waits for five matching votes.

## Privacy

- Only embeddings and 112 x 112 thumbnails are stored, encrypted. See
  [security.md](security.md#face-data).
- Register other people only with their consent.
- *Faces > Privacy > Delete all faces* removes every person and the encrypted file.

## Limits

- There is no liveness check: a printed photo or a phone screen showing a registered person
  is accepted. Do not rely on it to protect anything.
- Recognition gets worse with strong backlight, heavy shadows or the face far from the
  camera.
