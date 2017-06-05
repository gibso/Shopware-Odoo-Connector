Shopware Connector
==================

Dies ist der erste Prototyp des Shopware-Odoo-Konnektors.
Im Rahmen einer wissenschaftlichen Arbeit wurde dieser aus dem `Magento-Odoo-Konnektor`_ von `Camptocamp`_ migriert.
Er basiert auf dem `Connector`_ Framework und ist `verfügbar auf GitHub`_.

Bisherige Features:

* Import der Metadaten des Systems, bestehend aus den Shopware Shops
* Import der Kategorien von Artikeln
* Import der Artikel, mit Varianten
* Export der Bestandsmengen von bestehenden Varianten, mit Konfiguration des Lagerhauses und der Auswahl des zu benutzenden Bestand-Feldes

Bisher (noch) nicht unterstützte Features:

* Import der Kundendaten
* Import der Kundengruppen
* Import der Artikelbilder
* Import der Bestell-Aufträge
* Export des Lieferstatus von bestehenden Bestell-Aufträgen

Technische Punkte:

* Gebaut auf dem `connector`_ Framework
* Verwendet das Job-System des `connector`_ Frameworks
* Unterstützt bisher Shopware 5.2+ und Odoo 8.0

.. _Magento-Odoo-Konnektor: http://odoo-magento-connector.com/
.. _Connector: https://github.com/OCA/connector
.. _Camptocamp: http://www.camptocamp.com
.. _`verfügbar auf GitHub`: https://github.com/gibso/Shopware-Odoo-Connector

Installation und Konfiguration
==============================

Lesen Sie die Anleitung auf GitHub:
https://github.com/gibso/Shopware-Odoo-Connector

Autor
=====
Entwickelt von `Oliver Görtz`_.

.. _`Oliver Görtz`: https://www.xing.com/profile/Oliver_Goertz9

Sie können mich über `GitHub`_, `XING`_ und `Facebook`_ erreichen.

.. _`GitHub`: https://github.com/gibso
.. _`XING`: https://www.xing.com/profile/Oliver_Goertz9
.. _`Facebook`: https://www.facebook.com/ogoertz