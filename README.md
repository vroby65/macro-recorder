# Macro Recorder

Piccola finestra Linux con tre pulsanti:

- `● REC` cancella la macro precedente e avvia subito la registrazione;
- `▶ PLAY` riproduce la macro in loop; dopo 5 secondi, qualsiasi movimento,
  click o tocco fisico del puntatore interrompe la riproduzione;
- `■ STOP` ferma registrazione o riproduzione.

Le posizioni del mouse sono registrate come coordinate assolute e vengono
riprodotte nello stesso punto indipendentemente dalla posizione iniziale del
cursore. Tastiera e monitor di arresto usano `evdev`. La tastiera viene
riprodotta tramite `uinput`; posizione, click e rotella condividono il
controller Xorg di `pynput`.

La cattura e il posizionamento globale assoluto usano il backend Xorg di
`pynput`. Su Wayland puro l'accesso globale al puntatore è intenzionalmente
limitato: tramite XWayland può funzionare solo parzialmente e dipende dal
compositor.

## Installazione

Su Linux Mint, Ubuntu o Debian:

```bash
sudo apt install python3-evdev python3-pynput python3-tk
```

In alternativa, usando un ambiente virtuale:

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
```

Avvio diretto dalla cartella del progetto:

```bash
python3 -m macro_recorder
./macro-recorder
```

Dopo l'installazione con `pip` è disponibile anche il comando:

```bash
macro-recorder
```

## Permessi Linux

L'applicazione deve poter leggere `/dev/input/event*` e scrivere su
`/dev/uinput`. Prima prova ad avviarla normalmente: alcune distribuzioni
assegnano già gli ACL necessari all'utente della sessione.

Se manca l'accesso, su distribuzioni che usano il gruppo `input`:

```bash
sudo usermod -aG input "$USER"
echo 'KERNEL=="uinput", GROUP="input", MODE="0660", OPTIONS+="static_node=uinput"' | sudo tee /etc/udev/rules.d/70-macro-recorder-uinput.rules
sudo udevadm control --reload-rules
sudo udevadm trigger --name-match=uinput
```

Poi termina e riapri la sessione. Non avviare l'interfaccia con `sudo`.
L'appartenenza al gruppo `input` permette di leggere tutti gli input della
sessione, incluse le password: concedila soltanto a utenti e programmi fidati.

## Limiti intenzionali

- La registrazione assoluta del puntatore richiede una sessione Xorg; Wayland
  puro non è supportato in modo completo.
- La macro rimane in memoria e viene persa chiudendo l'applicazione.
- Cambiare risoluzione o disposizione dei monitor dopo la registrazione può
  spostare le coordinate attese.
- Il click usato sul pulsante STOP viene rimosso automaticamente dalla fine
  della registrazione.

## Verifica

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q macro_recorder tests
```
