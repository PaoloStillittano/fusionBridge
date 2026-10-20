# FusionBridge — guida rapida

FusionBridge permette a un assistente locale, come Codex o Claude Code, di creare e modificare parti in Autodesk Fusion, verificarne la geometria ed esportarle. La seconda CLI prepara progetti Bambu Studio con preset installati e slicing reale.

**Oggi il percorso supportato è macOS; la preparazione di stampa riguarda Bambu Lab A1**, ugelli 0.4/0.2 mm e preset PLA/PETG compatibili. Il progetto comprende add-in, CLI e skill: non implementa un server MCP o un agente autonomo.

[README completo](../README.md) · [Installazione e problemi comuni](installation.md) · [Skill](../skill/fusion360/SKILL.md)

## Installazione

Servono Git, Python **3.9+** e Autodesk Fusion installato e aperto almeno una volta. Bambu Studio è necessario solo per preparare lo slicing; account cloud e stampante configurata servono per l'invio dall'interfaccia ufficiale.

```bash
git clone https://github.com/PaoloStillittano/fusionBridge.git
cd fusionBridge
./install.sh --dry-run
./install.sh --agent codex
export PATH="$HOME/.local/bin:$PATH"
```

Puoi scegliere `--agent claude`, `--agent both` oppure `--agent none` per usare soltanto le CLI. L'installer crea collegamenti nella cartella utente, senza scaricare programmi, sostituire file estranei o modificare la configurazione della shell. La cartella clonata deve restare al suo posto.

In Fusion: **Utilities → Add-Ins → Scripts and Add-Ins → Add-Ins → FusionBridge → Run**. Se non compare, usa **+** e seleziona `addin/FusionBridge` dalla cartella clonata. Poi verifica:

```bash
f360 ping
b360 doctor
```

`doctor` controlla Studio e la CLI, non l'account cloud o lo stato della stampante.

## Primo esempio

Dalla cartella della repo, con Fusion e add-in attivi:

```bash
f360 new
f360 exec examples/plate.py
f360 tree
f360 shot -o outputs/plate.png -v iso,front,top
f360 fdm --bed 256x256x256 --strict
f360 export outputs/plate.stl
b360 prepare outputs/plate.stl --out outputs/jobs/plate-01 \
  --nozzle 0.4 --purpose balanced --plate textured --supports none
b360 inspect outputs/jobs/plate-01/project.3mf
b360 handoff outputs/jobs/plate-01
```

L'esempio crea una piastra **40 × 30 × 4 mm**, con due fori passanti da **3.4 mm** a interasse **24 mm**. Lo spessore è parametrico; le dimensioni dello schizzo sono numeriche. Lo script rifiuta documenti non vuoti. Apri le immagini e controlla il risultato prima dello slicing.

Il comando usa il filamento predefinito del preset macchina: per sceglierne un altro, cerca i nomi con `b360 presets filament --search PLA` e passa `--filament 'NOME ESATTO'`. Verifica che ugello, materiale e piatto corrispondano alla tua dotazione reale. Ogni lavoro richiede una cartella nuova.

`handoff` restituisce il progetto verificato: non apre Studio, non carica file e non stampa. Apri il 3MF **come progetto** in Bambu Studio, controlla Preview e seleziona la stampante nell'interfaccia **Print plate**. L'invio cloud e il completamento fisico non sono ancora stati collaudati: [limiti verificati](../VERIFICATION.md).

## Uso su progetti esistenti e dati privati

Su un documento esistente, copia `document_id` da `f360 ping` o `tree` e usa `f360 --document-id ID ...`: impedisce di modificare un documento diverso se cambia quello attivo.

I controlli geometrici e i preset non certificano resistenza o ottimalità. Un timeout non garantisce l'annullamento del comando; controlla lo stato prima di ripeterlo. `b360 record` registra osservazioni effettive e `status` legge il registro locale, senza telemetria live.

Salva modelli personali, foto, export, screenshot e lavori di stampa sotto `outputs/` o fuori dalla repo. Non pubblicare credenziali, file di connessione o log non ripuliti. Le regole per contributori e agenti sono in [AGENTS.md](../AGENTS.md).

Per disinstallare i collegamenti: `./install.sh --uninstall --dry-run`, poi `./install.sh --uninstall`. Codice, modelli e dati delle applicazioni vengono conservati.
