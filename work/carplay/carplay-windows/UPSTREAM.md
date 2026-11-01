The wired iAP2 control client and deadline helper are ported from
[DiPlay v0.2.7](https://github.com/shihabal3amri/DiPlay/tree/v0.2.7),
`shared/src/main/java/com/shilapi/xcertplay/transport/`.
They retain DiPlay's GPL-3.0 licensing; see the GPL-3.0 licence included with
PlayPort at `../playport/LICENSE`.

The Windows USB probe, USB configuration script and Apple USB carkit pipe are
new code for this emulator. The carkit pipe reads only the existing local Apple
pairing record for the attached phone and pins the device's TLS certificate.
Pairing certificates/private keys must never be logged or distributed.
