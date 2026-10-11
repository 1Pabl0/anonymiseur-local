from anonymiseur import Anonymizer, deanonymize


def anon(text, **kw):
    return Anonymizer(use_ner=False, **kw)


def types_and_texts(text, **kw):
    return [(e.type, e.text) for e in anon(text, **kw).detect(text)]


def test_email():
    assert ("EMAIL", "jean.dupont@example.com") in types_and_texts(
        "Écrire à jean.dupont@example.com."
    )


def test_iban_spaced_and_compact():
    spaced = "IBAN FR76 3000 6000 0112 3456 7890 189 merci"
    compact = "IBAN FR7630006000011234567890189 merci"
    assert types_and_texts(spaced) == [("IBAN", "FR76 3000 6000 0112 3456 7890 189")]
    assert types_and_texts(compact) == [("IBAN", "FR7630006000011234567890189")]


def test_phone_variants_share_one_label():
    text = "Tel 06 12 34 56 78 ou +33 6 12 34 56 78 ou 06.12.34.56.78"
    res = anon(text).anonymize(text)
    assert res.text == "Tel [TELEPHONE_1] ou [TELEPHONE_1] ou [TELEPHONE_1]"


def test_nir():
    assert ("NUM_SECU", "1 85 05 78 006 084 36") in types_and_texts(
        "Sécu : 1 85 05 78 006 084 36."
    )


def test_card_requires_luhn():
    assert ("CARTE", "4111 1111 1111 1111") in types_and_texts("CB 4111 1111 1111 1111")
    assert not [t for t in types_and_texts("réf 4111 1111 1111 1112") if t[0] == "CARTE"]


def test_address_with_city_is_one_entity():
    found = types_and_texts("Il habite 12 rue de la Paix, 75002 Paris depuis 2019.")
    assert found == [("ADRESSE", "12 rue de la Paix, 75002 Paris")]


def test_address_false_positives():
    assert types_and_texts("Il reste 3 places disponibles et 2 cours de maths.") == []


def test_title_name():
    found = types_and_texts("Mme Dupont a signé. M. Jean Martin a relu.")
    assert ("PERSONNE", "Mme Dupont") in found
    assert ("PERSONNE", "M. Jean Martin") in found


def test_extra_terms_case_insensitive():
    text = "Le projet phoenix et Acme Industries."
    found = types_and_texts(text, extra_terms=["Projet Phoenix", "Acme Industries"])
    assert found == [("TERME", "projet phoenix"), ("TERME", "Acme Industries")]


def test_no_false_positive_on_plain_text():
    text = "Article 12 : le contrat est résilié avec un préavis de 3 mois, soit 50 000 euros."
    assert types_and_texts(text) == []


def test_iban_is_not_split_into_other_types():
    assert [t for t, _ in types_and_texts("FR76 3000 6000 0112 3456 7890 189")] == ["IBAN"]


def test_consistent_labels_for_repeated_values():
    text = "a@x.fr puis b@x.fr puis a@x.fr"
    assert anon(text).anonymize(text).text == "[EMAIL_1] puis [EMAIL_2] puis [EMAIL_1]"


def test_round_trip():
    text = (
        "Bonjour Mme Martin, IBAN FR76 3000 6000 0112 3456 7890 189, "
        "mail jean@example.com, tel 06 12 34 56 78, 12 rue de la Paix, 75002 Paris."
    )
    a = anon(text)
    res = a.anonymize(text)
    assert "jean@example.com" not in res.text and "FR76" not in res.text
    assert deanonymize(res.text, res.mapping).text == text


def test_deanonymize_tolerates_lost_brackets_and_case():
    mapping = {"PERSONNE_1": "Mme Dupont", "NUM_SECU_1": "1 85 05 78 006 084 36"}
    out = deanonymize("Voir PERSONNE_1 et [personne_1], sécu : num_secu_1.", mapping)
    assert out.text == "Voir Mme Dupont et Mme Dupont, sécu : 1 85 05 78 006 084 36."


def test_unknown_labels_are_reported_and_left_untouched():
    out = deanonymize("Contactez [PERSONNE_7] ou var_1.", {"PERSONNE_1": "X"})
    assert out.text == "Contactez [PERSONNE_7] ou var_1."
    assert out.unknown_labels == ["PERSONNE_7"]  # var_1 n'est pas une de nos étiquettes


def test_mapping_reuse_across_documents():
    a = anon("")
    first = a.anonymize("a@x.fr")
    second = a.anonymize("b@x.fr puis a@x.fr", first.mapping)
    assert second.text == "[EMAIL_2] puis [EMAIL_1]"


def test_same_person_with_and_without_title_shares_label():
    text = "Mme Claire Martin a signé. Dossier suivi par Claire Martin."
    res = anon(text).anonymize(text)
    # Le 2e « Claire Martin » n'est pas détecté sans spaCy ; on teste donc la normalisation directement.
    from anonymiseur.core import _normalize
    assert _normalize("PERSONNE", "Mme Claire Martin") == _normalize("PERSONNE", "Claire Martin")
    assert res.text.startswith("[PERSONNE_1] a signé.")
