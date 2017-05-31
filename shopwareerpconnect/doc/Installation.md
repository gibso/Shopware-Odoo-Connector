# Installation

## Shopware
Bisher wird nur Shopware 5.2+ von dem Konnektor unterstützt.

### Plugin zur API Erweiterung
 Shopware muss mit dem Plugin *OdooApiExtension* erweitert werden. Das Plugin kann von GitHub mit dem Befehl,
 ```
$ git clone git@github.com:gibso/OdooApiExtension.git
```

heruntergeladen werden. Nachdem der enthaltene Ordner *OdooApiExtension* in der Shopware-Installation in das Verzeichnis `../Shopware_Wurzelverzeichnis/custom/plugins/`
verschoben wurde, wird das Plugin im Shopware-Backend unter Einstellungen -> Plugin-Manager installiert und aktiviert.


API-Zugang aktivieren
 Ein neuer Backend-Nutzer muss mit dem Recht des
Zugangs zerverwaltung zur API unter erstellt Einstellungen
 werden. Dazu 
 Benutzerverwaltung wird im Shopware-Backend geönet und die auf Benut-
 den
3 https://developers.shopware.com/sysadmins-guide/
KAPITEL 4.
 ANWENDUNG
 41
Abbildung 4.3: Anlegen des API Benutzers im Shopware Backend
Button Benutzer hinzufügen geklickt. Es önet sich ein Formular für einen neu-
en Benutzer. Dort wird im Abschnitt Login im Feld Benutzername api_user
eingetragen, ein beliebiges Passwort vergeben und die Aktiviert -Checkbox an-
gehakt. Im Abschnitt API-Zugang setzt man ebenfalls einen Haken in die Ak-
tiviert -Checkbox. Der erzeugte API-Schlüssel wird zusammen mit dem Nutzer-
namen später bei der Konguration des Konnektors benötigt (siehe Abschnitt
4.2.2). Im Abschnitt Stammdaten müssen beliebige Daten in die Felder Name
und E-Mail-Adress e eingetragen werden, und die Auswahl Mitglied der Rolle
muss mit local_admins belegt sein. Die Ausfüllung des Formulars ist in Abbil-
dung 4.3 zu betrachten.
