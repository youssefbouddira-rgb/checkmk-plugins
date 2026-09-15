# HITACHI VSP — Supervision CheckMK

Supervision des baies de stockage Hitachi VSP via le plugin communautaire
**"Hitachi VSP Storage Plugin"** 

## Contenu de ce dossier

| Fichier | Description |
|---|---|
| `hitachivsp-1.0.1.mkp` | Package CheckMK **original**, tel que téléchargé depuis le [CheckMK Exchange](https://exchange.checkmk.com/p/hitachivsp-3). Version 1.0.1, testé par l'auteur sur Hitachi VSP E590. |
| `agent_hitachi_vsp.py` | Script Special Agent **patché** — version corrigée pour fonctionner sur les baies **Hitachi VSP One Block (série B26 et probablement les autres modèles One Block)**. Remplace le fichier `libexec/agent_hitachi_vsp` du MKP original. |

## Pourquoi un patch ?

Le plugin original interroge l'API REST **Configuration Manager** de la baie
(`https://<adresse_baie>/ConfigurationManager/v1/objects/...`). Ce chemin
d'API est identique sur VSP One Block — **le plugin fonctionne donc sans
modification pour la capacité** (pools, LDEV, groupes de parité, CLPR, infos
système).

En revanche, l'endpoint matériel `/ConfigurationManager/v1/objects/components/instance`
renvoie une structure JSON différente sur VSP One Block par rapport aux
gammes E/G classiques sur lesquelles le plugin a été développé :

- Les tables matérielles (`ctls`, `cacheMemories`, `chbs`,
  `cacheFlashMemories`, `dkbs`, `sfps`, `bkmfs`) sont nichées sous une clé
  `dkcs` (liste de contrôleurs DKC), et non plus exposées à la racine du
  JSON.
- Le champ `recomendReplacement` (recommandation de remplacement disque)
  est absent des objets `drives` sur cette gamme.

Sans correctif, l'agent plante avec `KeyError: 'ctls'` (agent en échec
total) et/ou un warning de parsing sur la section
`hitachivsp_drive_boxes_drives` (colonne manquante).


### . Remplacer le script agent par la version patchée

Le fichier est déployé par le MKP à cet emplacement (adapter `<site>`) :

```
/omd/sites/<site>/local/lib/python3/cmk_addons/plugins/hitachi_vsp/libexec/agent_hitachi_vsp
```

Copier `agent_hitachi_vsp.py` de ce dépôt vers ce chemin **en conservant le
nom sans extension** (`agent_hitachi_vsp`, pas `.py`) et les droits
d'exécution :


## ⚠️ Point d'attention

Ce fichier `agent_hitachi_vsp` étant un composant du package `hitachivsp`,
toute opération `mkp update` / `mkp disable` + `mkp enable` /
réinstallation du MKP **écrasera le patch** et fera régresser la
supervision matérielle (retour du `KeyError: 'ctls'`). Après toute
opération de ce type sur le paquet, **redéployer la version patchée** de
ce dépôt.

## Compatibilité validée

- **Hitachi VSP One B26** — testé et validé (52 services actifs :
  capacité, matériel, consommation électrique).
