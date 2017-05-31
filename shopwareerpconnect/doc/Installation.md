# Installation

## Shopware
Bisher wird nur Shopware 5.2+ von dem Konnektor unterstützt.

### Plugin zur API Erweiterung
 Shopware muss mit dem Plugin *OdooApiExtension* erweitert werden. Das Plugin kann von GitHub mit dem Befehl,
```
$ git clone git@github.com:gibso/OdooApiExtension.git
```

heruntergeladen werden. Nachdem der enthaltene Ordner *OdooApiExtension* in der
Shopware-Installation in das Verzeichnis `../Shopware_Wurzelverzeichnis/custom/plugins/`
verschoben wurde, wird das Plugin im Shopware-Backend unter *Einstellungen* -> *Plugin-Manager* installiert und aktiviert.


### API-Zugang aktivieren
Ein neuer Backend-Nutzer muss mit dem Recht des Zugangs zur API erstellt werden. Dazu wird im Shopware-Backend
die Benutzerverwaltung unter *Einstellungen* -> *Benutzerverwaltung* geöffnet und auf den Button *Benutzer hinzufügen*
geklickt. Es öffnet sich ein Formular für einen neuen Benutzer. Dort wird im Abschnitt *Login* im Feld *Benutzername*
"api_user" eingetragen, ein beliebiges Passwort vergeben und die Aktiviert-Checkbox angehakt.
Im Abschnitt *API-Zugang* setzt man ebenfalls einen Haken in die Aktiviert-Checkbox. Der erzeugte API-Schlüssel
wird zusammen mit dem Nutzernamen später bei der [Konfguration](https://github.com/gibso/Shopware-Odoo-Connector/blob/master/shopwareerpconnect/doc/Konfiguration.md)
des Konnektors benötigt. Im Abschnitt *Stammdaten* müssen beliebige Daten in die Felder Name und E-Mail-Adresse
eingetragen werden, und die Auswahl Mitglied der Rolle muss mit *local_admins* belegt sein.

## Odoo
Bisher wird nur Odoo 8.0 unterstützt.

### Python Paketabhängigkeiten
Der Konnektor setzt in der Python-Bibliothek das Paket *shopware_rest* voraus. Mit folgendem Befehl wird es von
GitHub installiert:
```
$ pip install git+https://github.com/micronax/python-shopware-rest-client.git
```

### Odoo-Module herunterladen
Nun müssen das [Connector-Framework](https://github.com/OCA/connector) von [Camptocamp](http://www.camptocamp.com/) und seine Abhängigkeiten mit folgenden Befehlen von GitHub heruntergeladen werden:

```
$ git clone git@github.com:OCA/connector.git -b 8.0
$ git clone git@github.com:OCA/connector-ecommerce.git -b 8.0
$ git clone git@github.com:OCA/e-commerce.git -b 8.0
$ git clone git@github.com:OCA/product-attribute.git -b 8.0
$ git clone git@github.com:OCA/sale-workflow.git -b 8.0

```

Den Shopware-Odoo-Konnektor lädt man ebenfalls über GitHub mit dem folgenden Befehl herunter:
```
$ git clone git@github.com:gibso/Odoo-Shopware-Connector.git
```

### Odoo-Module einbinden
Die Verzeichnisse der heruntergeladenen Module werden als Pfade für die Odoo-Module in die Server-Konfgurationsdatei von
Odoo eingefügt oder beim Start des Odoo-Servers in der Kommandozeile mit angegeben.
Nachdem der Odoo-Server gestartet wurde, muss die Modulliste in Odoo aktualisiert werden.
Dazu benötigt der eingeloggte Administrator jedoch eine erweiterte technische Einsicht in die Einstellungen.
Um diese zu aktivieren klickt man unter *Einstellungen* im linken Seitenmenü auf *Benutzer* und wählt dort
den betreffenden Nutzer in der Tabelle aus. Daraufhin öffnet sich seine Einzelansicht.
Nach einem Klick auf den *Barbeiten*-Button, setzt man im Abschnitt *Bedienbarkeit* einen Haken hinter
*Technische Eigenschaften* und klickt auf den *Speichern*-Button. Um die neue Einstellung zu übernehmen,
muss die Seite einmal neu geladen werden durch den Browser. Nun kann unter Einstellungen im
Seitenmenüabschnitt *Module* auf *Update Modulliste* geklickt werden und in dem
sich öffnenden Fenster auf *Aktualisieren*.

### Odoo-Module installieren
In Odoo klickt man unter *Einstellungen* im Seitenmenüabschnitt *Module* auf *Lokale Apps*.
Dort sucht man in der Suchleiste oben rechts nach dem Modul *Shopware Connector* und installiert das gefundene
Modul mit einem Klick auf *Installieren*. Die Installation kann einige Minuten in
Anspruch nehmen. Nach der Installation und einem erneuten Laden der Seite
erscheint der neue Menüpunkt *Connector* in der Hauptmenüleiste.
