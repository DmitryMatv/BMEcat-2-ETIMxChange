import logging
from typing import Optional

import orjson
from lxml import etree
import jsonschema_rs



def remove_namespaces(root):
    """
    Recursively remove namespaces from the XML tree.
    """
    for elem in root.getiterator():
        # Only process element nodes (skip comments, etc.)
        if isinstance(elem.tag, str):
            # Remove the namespace by splitting on the '}' character.
            if '}' in elem.tag:
                elem.tag = elem.tag.split('}', 1)[1]
    return root

def convert_BMEcat(XML_path):
    """
    Parse an ETIM BMEcat XML file and convert it to ETIM xChange JSON format.

    Args:
        XML_path (str): Path to the input BMEcat XML file.

    Returns:
        Dict[str, Any]: A dictionary representing the ETIM xChange JSON structure.

    Raises:
        FileNotFoundError: If the XML file does not exist.
        ValueError: If mandatory fields are missing or invalid.
    """
    
    print("Loading BMEcat...")
    root = etree.parse(XML_path).getroot()
    
    BMECAT = remove_namespaces(root)

    HEADER = BMECAT.find("HEADER")
    CATALOG = BMECAT.find(".//T_NEW_CATALOG")
    if CATALOG is None:
        CATALOG = BMECAT.find(".//T_NEW_PRODUCTDATA") 

    def get_val(target_field, XML_root, val_type=str):
        """Return the text of the first matching element.
        
        Args:
            target_field: The field name to search for
            XML_root: The XML root element
            val_type: The type to convert the value to (str, bool, or int)
            
        Returns:
            The value converted to the specified type, or None if not found
        """
       
        element = XML_root.findtext(f".//{target_field}") # try using just .find ?
        
        if element is not None:
            # Strip whitespace
            element = element.strip()
            
            # Return None if the element is just a hyphen
            if element.startswith("-"):
                return None
                
            # Handling val_type
            if val_type == bool:
                return element.lower() == "true"
            if val_type == int:
                return int(element) if element else None
                
            return element
        return None  # Explicitly return None if no matching element found

    def get_val_attr(target_field, XML_root, val_type=str, **attributes):
        """Return the text of the first matching element with specified attributes.
        
        Args:
            target_field: The field name to search for
            XML_root: The XML root element
            val_type: The type to convert the value to (str, bool, or int)
            **attributes: Attribute filters to apply
            
        Returns:
            The value converted to the specified type, or None if not found
        """
        
        xpath_query = f".//{target_field}"

        # If we want elements that specifically DON'T have a lang attribute
        if 'no_lang' in attributes and attributes['no_lang'] is True:
            xpath_query += "[not(@lang)]"
            # Remove the no_lang from attributes since it's not a real XML attribute
            attributes.pop('no_lang')

        # If any attribute filters are provided, add them to the query
        if attributes:
            # Create a list of conditions like "@id='main'"
            conditions = [f"@{attr}='{value}'" for attr, value in attributes.items()]
            # Join conditions with 'and' (all conditions must be met)
            xpath_query += "[" + " and ".join(conditions) + "]"
        
        
        # Add the text() node to retrieve the element's text content
        xpath_query += "/text()"

        # Run the XPath query on the XML tree
        xpath_val = XML_root.xpath(xpath_query)

        # Return the first matching text value, or None if no match
        if xpath_val:
            element = xpath_val[0].strip()
            
            # Return None if the element is just a hyphen
            if element.startswith("-"):
                return None
                
            # Handling val_type
            if val_type == bool:
                return element.lower() == "true"
            if val_type == int:
                return int(element) if element else None
                
            return element
        return None
     
    xChange = {
        "CatalogueId": get_val("CATALOG_ID", HEADER) or get_val("CATALOG_NAME", HEADER), # Mandatory
        "CatalogueName": [],
        "CatalogueVersion": get_val("CATALOG_VERSION", HEADER),
        #"ContractReferenceNumber": "",
        "CatalogueType": "FULL", # Mandatory FULL or PART
        #"ChangeReferenceCatalogueVersion" : "",
        "GenerationDate": get_val("DATE", HEADER),
        "NameDataCreator": get_val("GENERATOR_INFO", HEADER), 
        "EmailDataCreator": get_val("EMAIL", HEADER),
        "BuyerName": get_val("BUYER_NAME", HEADER),
        "BuyerIdGln": get_val_attr("BUYER_ID", HEADER, type="gln"),
        #"BuyerIdDuns": "",
        #"DatapoolName": "",
        #"DatapoolGln": "",
        "CatalogueValidityStart": get_val("DATE", HEADER) or get_val("UDX.EDXF.VALID_FROM", CATALOG) or "1971-08-15", # Mandatory
        #"CatalogueValidityEnd": "",
        "Country": [get_val("TERRITORY", HEADER)],
        "Language": [], # Mandatory
        "CurrencyCode": get_val("CURRENCY", HEADER),
        #"CountrySpecificExtensions": [], # {}?
        "Supplier": []
    }
       
       
    def convert_to_language_region_code(iso_code: Optional[str]) -> Optional[str]:
        """
        Convert ISO 639-2 language code (both bibliographic and terminological) to language-region code format.
        
        Args:
            iso_code (str): ISO 639-2/B (bibliographic) or ISO 639-2/T (terminological) language code (3-letter code)
            
        Returns:
            str: Language-region code (e.g., 'de-DE' for German)
            
        Raises:
            ValueError: If the ISO code is not supported or invalid
        """
        # Mapping of ISO 639-2 codes to language-region codes
        # This includes both bibliographic and terminological codes where they differ
        iso_to_lang_region = {
            # Germanic languages
            "deu": "de-DE",  # German (T)
            "ger": "de-DE",  # German (B)
            "eng": "en-GB",  # English (same for B and T)
            "nld": "nl-NL",  # Dutch (T)
            "dut": "nl-NL",  # Dutch (B)
            "swe": "sv-SE",  # Swedish (same for B and T)
            "nor": "no-NO",  # Norwegian (same for B and T)
            "dan": "da-DK",  # Danish (same for B and T)
            "isl": "is-IS",  # Icelandic (T)
            "ice": "is-IS",  # Icelandic (B)
            
            # Romance languages
            "fra": "fr-FR",  # French (T)
            "fre": "fr-FR",  # French (B)
            "ita": "it-IT",  # Italian (same for B and T)
            "spa": "es-ES",  # Spanish (same for B and T)
            "por": "pt-PT",  # Portuguese (same for B and T)
            "ron": "ro-RO",  # Romanian (T)
            "rum": "ro-RO",  # Romanian (B)
            
            # Slavic languages
            "rus": "ru-RU",  # Russian (same for B and T)
            "pol": "pl-PL",  # Polish (same for B and T)
            "ces": "cs-CZ",  # Czech (T)
            "cze": "cs-CZ",  # Czech (B)
            "slk": "sk-SK",  # Slovak (T)
            "slo": "sk-SK",  # Slovak (B)
            "ukr": "uk-UA",  # Ukrainian (same for B and T)
            "bul": "bg-BG",  # Bulgarian (same for B and T)
            
            # Asian languages
            "jpn": "ja-JP",  # Japanese (same for B and T)
            "zho": "zh-CN",  # Chinese (T)
            "chi": "zh-CN",  # Chinese (B)
            "kor": "ko-KR",  # Korean (same for B and T)
            "tha": "th-TH",  # Thai (same for B and T)
            "vie": "vi-VN",  # Vietnamese (same for B and T)
            
            # Other European languages
            "ell": "el-GR",  # Greek (T)
            "gre": "el-GR",  # Greek (B)
            "hun": "hu-HU",  # Hungarian (same for B and T)
            "fin": "fi-FI",  # Finnish (same for B and T)
            "tur": "tr-TR",  # Turkish (same for B and T)
            
            # Middle Eastern languages
            "ara": "ar-SA",  # Arabic (same for B and T)
            "heb": "he-IL",  # Hebrew (same for B and T)
            "fas": "fa-IR",  # Persian (T)
            "per": "fa-IR",  # Persian (B)
            
            # South Asian languages
            "hin": "hi-IN",  # Hindi (same for B and T)
            "ben": "bn-BD",  # Bengali (same for B and T)
            "tam": "ta-IN",  # Tamil (same for B and T)
            
            # Others
            "swa": "sw-KE",  # Swahili (same for B and T)
            "ind": "id-ID",  # Indonesian (same for B and T)
            "msa": "ms-MY",  # Malay (T)
            "may": "ms-MY",  # Malay (B)
            
            # Others with B/T differences
            "hye": "hy-AM",  # Armenian (T)
            "arm": "hy-AM",  # Armenian (B)
            "kat": "ka-GE",  # Georgian (T)
            "geo": "ka-GE",  # Georgian (B)
            "eus": "eu-ES",  # Basque (T)
            "baq": "eu-ES",  # Basque (B)
            "slv": "sl-SI",  # Slovenian (same for B and T)
            "mri": "mi-NZ",  # Maori (T)
            "mao": "mi-NZ",  # Maori (B)
            "mya": "my-MM",  # Burmese (T)
            "bur": "my-MM",  # Burmese (B)
            "mkd": "mk-MK",  # Macedonian (T)
            "mac": "mk-MK",  # Macedonian (B)
            "cym": "cy-GB",  # Welsh (T)
            "wel": "cy-GB",  # Welsh (B)
            "alb": "sq-AL",  # Albanian (B)
            "sqi": "sq-AL",  # Albanian (T)
        }
        
        # Validate input
        #if not isinstance(iso_code, str) or len(iso_code) != 3:
        #    raise ValueError("ISO code must be a 3-letter string")
        
        if iso_code is None:
            return None
        
        iso_code = iso_code.strip().lower()
        
        if iso_code not in iso_to_lang_region:
            raise ValueError(f"Unsupported ISO 639-2 code: {iso_code}")
        
        # Country from BMEcat insted of default country for a given lang
        #if Country is not None:
        #    lang_region = iso_to_lang_region[iso_code]
        #    return lang_region[:-2] + Country
        
        return iso_to_lang_region[iso_code]     

    # Default catalog language
    DefaultLangXPath = HEADER.xpath('.//LANGUAGE[@default="true"]/text()')
    if DefaultLangXPath:  # This checks if the list is non-empty
        DefaultLangBMEcat = DefaultLangXPath[0]
    elif HEADER.findtext(".//LANGUAGE") is not None:
        DefaultLangBMEcat = get_val("LANGUAGE", HEADER)
    else:
        DefaultLangBMEcat = None  # Fallback to a default
    DefaultLangxChange = convert_to_language_region_code(DefaultLangBMEcat)
    #print(DefaultLangxChange)    
    
    # All catalog languages
    LANGUAGEs = []
    if HEADER.findtext(".//LANGUAGE") is not None:
        for LANGUAGE in HEADER.iterfind(".//LANGUAGE"):
            LANGUAGEs.append(LANGUAGE.text)
            xChange["Language"].append(convert_to_language_region_code(LANGUAGE.text))
    else:
        xChange["Language"].append(DefaultLangxChange)
    #print(LANGUAGEs)
    
    def append_multilingual_elements(parent_element, xpath_query, target, entry_key, default_lang=DefaultLangxChange):
        for element in parent_element.iterfind(xpath_query):
            lang_attr = element.xpath("@lang")
            language = convert_to_language_region_code(lang_attr[0]) if lang_attr else default_lang
            target.append({
                "Language": language, #language if len(CatalogLangs) >= 2  else None,
                entry_key: element.text
        })
    
    # Catalog name with language  
    append_multilingual_elements(HEADER, ".//CATALOG_NAME",
        xChange["CatalogueName"], "CatalogueName")


    Supplier = {
        "SupplierName": get_val("SUPPLIER_NAME", HEADER), # Mandatory
        "SupplierIdGln": get_val_attr("SUPPLIER_ID", HEADER, type="gln"),
        "SupplierIdDuns": get_val_attr("SUPPLIER_ID", HEADER, type="duns"),
        "SupplierVatNo": get_val("VAT_ID", HEADER),
        "SupplierAttachments": [],
        "Product": []
    }
    
    # CODES MAPPINGS
    def map_attachment_type(md_code: Optional[str]) -> Optional[str]:
        """Maps BMEcat MIME_CODE (MD) values to standardized AttachmentType (ATX) values.

        Args:
            md_code: The old MD code from UDX.EDXF.MIME_CODE or MIME_DESCR in header

        Returns:
            Mapped ATX attachment type code or None if no matching type found
        """
        
        ATTACHMENT_CODE_MAPPING = {
            # Product pictures
            "MD01": "ATX015",  # Product picture → Main product/item picture
            "MD02": "ATX018",  # Similar figure → Picture
            "MD20": "ATX018",  # Ambient picture → Picture
            "MD23": "ATX018",  # Product picture back view → Picture
            "MD24": "ATX018",  # Product picture bottom view → Picture
            "MD25": "ATX018",  # Product picture detailed view → Picture
            "MD26": "ATX018",  # Product picture front view → Picture
            "MD27": "ATX018",  # Product picture sloping → Picture
            "MD28": "ATX018",  # Product picture top view → Picture
            "MD29": "ATX018",  # Product picture view from the left side → Picture
            "MD30": "ATX018",  # Product picture view from the right side → Picture
            "MD47": "ATX018",  # Thumbnail of Product picture → Picture
            "MD48": "ATX018",  # Pictogram/Icon → Picture
            "MD59": "ATX018",  # Product picture square format → Picture
            "MD65": "ATX018",  # Product family view → Picture
            
            # Data sheets and technical information
            "MD03": "ATX019",  # Safety data sheet → Safety data sheet
            "MD07": "ATX003",  # Product data sheet for energy label → Data sheet
            "MD19": "ATX003",  # Luminaire data → Data sheet
            "MD22": "ATX003",  # Product data sheet → Data sheet
            "MD32": "ATX003",  # Technical information → Data sheet
            "MD40": "ATX003",  # Spare parts list → Data sheet
            "MD63": "ATX003",  # Specification text → Data sheet
            
            # Declarations
            "MD05": "ATX007",  # Declaration REACH → Declaration REACH
            "MD06": "ATX012",  # Energy label → Energy label
            "MD13": "ATX006",  # Environment label → Declaration EPD
            "MD49": "ATX008",  # Declaration RoHS → Declaration RoHS
            "MD51": "ATX005",  # Declaration DOP → Declaration DOP
            "MD52": "ATX004",  # Declaration DOC CE → Declaration (other)
            "MD53": "ATX004",  # Declaration BREEAM → Declaration (other)
            "MD54": "ATX006",  # Declaration EPD → Declaration EPD
            "MD55": "ATX004",  # Declaration ETA → Declaration (other)
            "MD56": "ATX021",  # Declaration warranty → Warranty statement
            
            # Certificates and approvals
            "MD08": "ATX001",  # Calibration certificate → Approval/certificate
            "MD09": "ATX001",  # Certificate → Approval/certificate
            "MD31": "ATX001",  # Seal of approval → Approval/certificate
            "MD33": "ATX001",  # Test approval → Approval/certificate
            "MD42": "ATX001",  # AVCP certificate → Approval/certificate
            "MD50": "ATX001",  # Declaration CoC → Approval/certificate
            
            # Diagrams and drawings
            "MD10": "ATX010",  # Circuit diagram → Diagram
            "MD12": "ATX011",  # Dimensioned drawing → Drawing
            "MD15": "ATX010",  # Light cone diagram → Diagram
            "MD16": "ATX010",  # Light Distribution Curve → Diagram
            "MD34": "ATX010",  # Wiring diagram → Diagram
            "MD60": "ATX011",  # Exploded view drawing → Drawing
            "MD61": "ATX010",  # Flowchart → Diagram
            "MD64": "ATX011",  # Line drawing → Drawing
            
            # Manuals and instructions
            "MD14": "ATX016",  # Instructions for use → Manual
            "MD21": "ATX016",  # Mounting instruction → Manual
            "MD38": "ATX016",  # Management, operation and maintenance document → Manual
            
            # Visual media
            "MD17": "ATX014",  # Logo 1c → Logo
            "MD18": "ATX014",  # Logo 4c → Logo
            "MD39": "ATX020",  # Instructional video → Video
            "MD45": "ATX020",  # Product video → Video
            "MD46": "ATX020",  # 360° view → Video
            "MD57": "ATX020",  # Application video → Video
            "MD58": "ATX020",  # Question and Answer (Q&A video) → Video
            
            # Special types
            "MD37": "ATX002",  # 3D / BIM object → BIM object
            "MD41": "ATX017",  # Sales brochure → Marketing document
            "MD62": "ATX017",  # Product presentation → Marketing document
            
            # Other classifications
            "MD11": "ATX004",  # Construction Products Regulation → Declaration (other)
            "MD35": "ATX004",  # Supplier's declaration for products having preferential origin status → Declaration (other)
            "MD43": "ATX004",  # CLP → Declaration (other)
            "MD44": "ATX004",  # ECOP → Declaration (other)
            
            # Miscellaneous
            "MD04": "ATX099",  # Deeplink product page → No direct match (others)
            "MD99": "ATX099",  # Others → Others
        }
        
        if md_code is None:
            return None
        
        # Upper and strip to handle case variations
        md_code = md_code.upper().strip()
        
        return ATTACHMENT_CODE_MAPPING.get(md_code, None)
    
    def map_relation_type(reference_type: Optional[str]) -> Optional[str]:
        """Maps BMEcat PRODUCT_REFERENCE type attribute values to standardized relation type codes.

        Args:
            reference_type: The value from the PRODUCT_REFERENCE/@type attribute in BMEcat
                        (e.g., 'accessories', 'base_product', 'consists_of', etc.)

        Returns:
            Mapped relation type code or None if no matching type found
            
        The mapping is based on BMEcat 2005 specification and ETIM xChange documentation:
        - accessories -> ACCESSORY (extends functionality)
        - base_product -> MAIN_PRODUCT (product this relates back to)
        - consists_of -> CONSISTS_OF (component parts/set components)
        - followup -> SUCCESSOR (more advanced version/replacement)
        - mandatory -> MANDATORY (required additional product)
        - similar -> SIMILAR (similar purpose/function)
        - select -> SELECT (optional but one must be chosen)
        - sparepart -> SPAREPART (replacement part)
        - others -> OTHER (no other type fits)
        """
        
        RELATION_TYPE_MAPPING = {
            "accessories": "ACCESSORY",
            "base_product": "MAIN_PRODUCT",
            "consists_of": "CONSISTS_OF", 
            "followup": "SUCCESSOR",  # Could also potentially map to UPSELLING
            "mandatory": "MANDATORY",
            "similar": "SIMILAR",
            "select": "SELECT",
            "sparepart": "SPAREPART",
            "others": "OTHER",
            
            # Handle possible variations in input
            "accessory": "ACCESSORY",
            "main": "MAIN_PRODUCT",
            "component": "CONSISTS_OF",
            "successor": "SUCCESSOR",
            "spare": "SPAREPART",
            "spare_part": "SPAREPART",
            "other": "OTHER"
        }
        
        if reference_type is None:
            return None
            
        # Convert to lowercase and strip to handle case variations
        reference_type = reference_type.lower().strip()
        
        return RELATION_TYPE_MAPPING.get(reference_type, None)

    def map_product_status(product_type: Optional[str]) -> Optional[str]:
        """Maps BMEcat product status type to standardized product status values.

        Args:
            product_type: The value from the PRODUCT_STATUS/@type attribute in BMEcat

        Returns:
            Mapped product status or None if no matching status found
        """
        
        PRODUCT_CODES_MAPPING = {
            # PRODUCT_STATUS type="core_product|new_product|old_product"
            # PRODUCT_STATUS type="new|refurbished|used"
            # ALLOWED VALUES: "PRE-LAUNCH"; "ACTIVE"; "ON HOLD"; "PLANNED WITHDRAWAL"; "OBSOLETE"
            "core": "ACTIVE",
            "core_product": "ACTIVE",
            
            "new": "ACTIVE",
            "new_product": "ACTIVE",
            
            "old": "OBSOLETE",
            "old_product": "OBSOLETE",
            
            "bargain": "ACTIVE",
            "used": "ACTIVE",
            "refurbished": "ACTIVE",
        
            #"others": "ACTIVE"
        }
        
        if product_type is None:
            return None
        
        # Convert to lowercase and strip to handle case variations
        product_type = product_type.lower().strip()
        
        return PRODUCT_CODES_MAPPING.get(product_type, None)

    # ETIM PROCESSING
    def extract_etim_version(text):
        """
        Extracts the version number from a string if it contains 'ETIM'.

        Args:
            text: A string like 'ETIM-9.0' or 'ECLASS-11.0'

        Returns:
            The version number as a string if 'ETIM' is found, None otherwise
        """
        if "ETIM" in text:
            # Find where ETIM ends, could be 'ETIM-' or 'ETIM '
            etim_pos = text.find("ETIM") + 4

            # Skip any non-digit characters (like '-' or spaces)
            while etim_pos < len(text) and not text[etim_pos].isdigit():
                etim_pos += 1

            # Extract the version (digits and dots)
            version = ""
            while etim_pos < len(text) and (
                text[etim_pos].isdigit() or text[etim_pos] == "."
            ):
                version += text[etim_pos]
                etim_pos += 1

            return version if version else None
        else:
            return None

    def extract_class_code(text):
        """
        Returns the text if it starts with 'EC', otherwise returns None.

        Args:
            text: A string like 'EC001545' or '27142301'

        Returns:
            The original text if it starts with 'EC', None otherwise
        """
        if text and text.startswith("EC"):
            return text
        else:
            return None

    def clean_number(value):
        """
        Convert float to int if it can be represented as a whole number.
        Otherwise return the original float as a string.

        Args:
            value: A numeric value (float or int)

        Returns:
            String representation of the number, with decimals removed if possible
        """
        try:
            float_val = float(value)
            if float_val.is_integer():
                return str(int(float_val))
            #return str(float_val)
            return f"{float_val:.4f}".rstrip('0').rstrip('.')
        except (ValueError, TypeError):
            return value
    
    def process_feature_values(feature_element, feature_xpath="./FVALUE"):
        """
        Process all FVALUE elements in a FEATURE element and determine appropriate value types.

        Args:
            feature_element: The FEATURE XML element

        Returns:
            Dictionary with appropriate EtimValue fields based on FVALUE content
        """
        result = {}

        # Collect all FVALUE elements
        fvalues = [
            fval.text.strip() if fval.text else ""
            for fval in feature_element.findall(feature_xpath)
        ]

        # Check for EV code values (starts with EV and exactly 8 chars)
        ev_codes = [val for val in fvalues if val.startswith("EV") and len(val) == 8]
        if ev_codes:
            result["EtimValueCode"] = ev_codes[0]

        # Check for numeric values for ranges
        numeric_values = []
        for val in fvalues:
            try:
                numeric_values.append(float(val))
            except (ValueError, TypeError):
                pass
        if len(numeric_values) == 2:
            result["EtimValueRangeLower"] = clean_number(min(numeric_values))
            result["EtimValueRangeUpper"] = clean_number(max(numeric_values))
        elif len(numeric_values) == 1:
            result["EtimValueNumeric"] = clean_number(numeric_values[0])

        # Check for boolean values
        bool_values = []
        for val in fvalues:
            val_lower = val.lower()
            if val_lower == "true":
                bool_values.append(True)
            elif val_lower == "false":
                bool_values.append(False)
        if bool_values:
            result["EtimValueLogical"] = bool_values[0]

        return result

    for SUPPLIER_MIME in HEADER.iterfind(".//MIME"):
        SupplierAttachments = {
            "AttachmentType": map_attachment_type(get_val("MIME_DESCR", SUPPLIER_MIME)) or "ATX099", # Mandatory
            "AttachmentDetails": [{
                "AttachmentLanguage": [DefaultLangxChange], # Mendatory if many languages !!!
                "AttachmentTypeSpecification": [],
                #"AttachmentFilename": "",
                "AttachmentUri": get_val("MIME_SOURCE", SUPPLIER_MIME),
                "AttachmentDescription": [],
                #"AttachmentIssueDate": "",
                #"AttachmentExpiryDate": "",
            }],
        }
        append_multilingual_elements(SUPPLIER_MIME, "MIME_DESCR", 
            SupplierAttachments["AttachmentDetails"][0]["AttachmentTypeSpecification"], "AttachmentTypeSpecification")
        append_multilingual_elements(SUPPLIER_MIME, "MIME_DESCR", 
            SupplierAttachments["AttachmentDetails"][0]["AttachmentDescription"], "AttachmentDescription")
        Supplier["SupplierAttachments"].append(SupplierAttachments)

    xChange["Supplier"].append(Supplier)


    print("Processing products...")
    product_counter = 0
    for BMECAT_PRODUCT in CATALOG.iterfind("./PRODUCT"):
        product_counter += 1
        if product_counter % 1000 == 0:
            print(f"Processed {product_counter} products...")
        
        Product = {
            "ProductIdentification": {},
            "ProductDetails": {},
            "ProductRelations": [],
            "Legislation": {},
            "ProductAttachments": [],
            "EtimClassification": [],
            "OtherClassifications": [],
            "ProductCountrySpecificFields": [],
            #"ProductCountrySpecificExtensions": [],
            "TradeItem": []
        }       
        
        UDX = BMECAT_PRODUCT.find(".//USER_DEFINED_EXTENSIONS")
        if UDX is None:
            UDX = BMECAT_PRODUCT
        
        ProductIdentification = {
            #"ManufacturerIdGln"
            #"ManufacturerIdGln"
            "ManufacturerName": get_val("MANUFACTURER_NAME", BMECAT_PRODUCT),
            "ManufacturerShortname": get_val("UDX.EDXF.MANUFACTURER_ACRONYM", UDX),
            "ManufacturerProductNumber": get_val("MANUFACTURER_PID", BMECAT_PRODUCT),
            "ProductGtin": [get_val("INTERNATIONAL_PID", BMECAT_PRODUCT)],
            #"UnbrandedProduct": {},
            "BrandName": get_val("UDX.EDXF.BRAND_NAME", UDX),
            "BrandDetails": [{"BrandSeries": [], "BrandSeriesVariation": []}],
            "ProductValidityDate": get_val("UDX.EDXF.VALID_FROM", UDX),
            "ProductObsolescenceDate": get_val("UDX.EDXF.EXPIRATION_DATE", UDX),
            "CustomsCommodityCode": get_val("CUSTOMS_NUMBER", BMECAT_PRODUCT),
            "FactorCustomsCommodityCode": get_val("STATISTICS_FACTOR", BMECAT_PRODUCT),
            "CountryOfOrigin": [get_val("COUNTRY_OF_ORIGIN", BMECAT_PRODUCT)],
        }
        append_multilingual_elements(UDX, "./UDX.EDXF.PRODUCT_SERIES",
            ProductIdentification["BrandDetails"][0]["BrandSeries"], "BrandSeries") 
        append_multilingual_elements(UDX, "./UDX.EDXF.PRODUCT_VARIATION",
            ProductIdentification["BrandDetails"][0]["BrandSeriesVariation"], "BrandSeriesVariation")   
        Product["ProductIdentification"].update(ProductIdentification)
    
    
        ProductDetails = {
            "ProductStatus": map_product_status(BMECAT_PRODUCT.xpath(".//PRODUCT_STATUS/@type")[0])
                if BMECAT_PRODUCT.xpath(".//PRODUCT_STATUS/@type") else None,   
            "ProductType": get_val("PRODUCT_TYPE", BMECAT_PRODUCT).upper() if get_val("PRODUCT_TYPE", BMECAT_PRODUCT) else None,
            #"CustomisableProduct": "",
            "ProductDescriptions": [
                {
                    "DescriptionLanguage": DefaultLangxChange,
                    "MinimalProductDescription": get_val_attr("UDX.EDXF.DESCRIPTION_VERY_SHORT", UDX, no_lang=True)
                        or get_val_attr("DESCRIPTION_SHORT", BMECAT_PRODUCT, no_lang=True)
                        or get_val_attr("UDX.EDXF.DESCRIPTION_VERY_SHORT", UDX, lang=DefaultLangBMEcat)
                        or get_val_attr("DESCRIPTION_LONG", BMECAT_PRODUCT, lang=DefaultLangBMEcat), 
                    "UniqueMainProductDescription": get_val_attr("DESCRIPTION_SHORT", BMECAT_PRODUCT, no_lang=True)
                        or get_val_attr("DESCRIPTION_SHORT", BMECAT_PRODUCT, lang=DefaultLangBMEcat),
                    "FullProductDescription": get_val_attr("DESCRIPTION_LONG", BMECAT_PRODUCT, no_lang=True)
                        or get_val_attr("DESCRIPTION_LONG", BMECAT_PRODUCT, lang=DefaultLangBMEcat),
                    #"ProductMarketingText": "",
                    "ProductSpecificationText": get_val_attr("UDX.EDXF.TENDER_TEXT", UDX, no_lang=True)
                        or get_val_attr("UDX.EDXF.TENDER_TEXT", UDX, lang=DefaultLangBMEcat),
                    "ProductApplicationInstructions": get_val_attr("REMARKS", BMECAT_PRODUCT, no_lang=True)
                        or get_val_attr("REMARKS", BMECAT_PRODUCT, lang=DefaultLangBMEcat),
                    "ProductKeyword": [kw.text.strip() for kw in BMECAT_PRODUCT.findall(".//KEYWORD")
                                       if kw.text and kw.text.strip()
                                       and ('lang' not in kw.attrib or kw.get('lang') == DefaultLangBMEcat)]
                    #"ProductPageUrl": ""
                }
            ],
            "WarrantyConsumer": get_val("UDX.EDXF.WARRANTY_CONSUMER", UDX, val_type=int),
            "WarrantyBusiness": get_val("UDX.EDXF.WARRANTY_BUSINESS", UDX, val_type=int)
        }
        
        if LANGUAGEs:
            for lang in LANGUAGEs:
                if lang and lang != DefaultLangBMEcat:
                    ProductDetails["ProductDescriptions"].append({
                        "DescriptionLanguage": convert_to_language_region_code(lang), 
                        "MinimalProductDescription": get_val_attr("UDX.EDXF.DESCRIPTION_VERY_SHORT", BMECAT_PRODUCT, lang=lang)
                            or get_val_attr("DESCRIPTION_SHORT", BMECAT_PRODUCT, lang=lang)
                            or get_val_attr("UDX.EDXF.DESCRIPTION_VERY_SHORT", BMECAT_PRODUCT)
                            or get_val_attr("DESCRIPTION_LONG", BMECAT_PRODUCT),
                        "UniqueMainProductDescription": get_val_attr("DESCRIPTION_SHORT", BMECAT_PRODUCT, lang=lang),
                        "FullProductDescription": get_val_attr("DESCRIPTION_LONG", BMECAT_PRODUCT, lang=lang),
                        #"ProductMarketingText": "",
                        "ProductSpecificationText": get_val_attr("UDX.EDXF.TENDER_TEXT", BMECAT_PRODUCT, lang=lang),
                        "ProductApplicationInstructions": get_val_attr("REMARKS", BMECAT_PRODUCT, lang=lang),
                        "ProductKeyword": [kw.text.strip() for kw in BMECAT_PRODUCT.findall(f".//KEYWORD[@lang='{lang}']")
                                           if kw.text and kw.text.strip()]
                        #"ProductPageUrl": ""
                    })
        
        Product["ProductDetails"].update(ProductDetails)
        
        
        for REFERENCE in BMECAT_PRODUCT.iterfind("./PRODUCT_REFERENCE"): 
                Product["ProductRelations"].append({
                    "RelatedManufacturerProductNumber": get_val("PROD_ID_TO", REFERENCE),
                    #"RelatedProductGtin": [],
                    "RelationType": map_relation_type(REFERENCE.xpath("@type")[0]) if REFERENCE.xpath("@type") else "OTHER",
                    "RelatedProductQuantity": int(REFERENCE.xpath("@quantity")[0]) if REFERENCE.xpath("@quantity") else 1
                })       
        
        
        Legislation = {
            #"ElectricComponentContained": "",
            "BatteryContained": get_val("UDX.EDXF.BATTERY_CONTAINED", UDX, val_type=bool),
            #"WeeeCategory": "",
            "RohsIndicator": get_val("UDX.EDXF.ROHS_INDICATOR", UDX),
            "CeMarking": get_val("UDX.EDXF.CE_MARKING", UDX, val_type=bool),
            "SdsIndicator": get_val_attr("SPECIAL_TREATMENT_CLASS", BMECAT_PRODUCT, val_type=bool, type="SDS"),
            "ReachIndicator": get_val("UDX.EDXF.REACH.INFO", UDX),
            "ReachDate": get_val("UDX.EDXF.REACH.LISTDATE", UDX),
            "ScipNumber": get_val("UDX.EDXF.SCIP_NUMBER", UDX),
            "UfiCode": get_val("UDX.EDXF.UFI_CODE", UDX),
            "UnNumber": get_val("UDX.EDXF.UN_NUMBER", UDX),
            "HazardClass": [get_val("UDX.EDXF.HAZARD_CLASS", UDX)],
            "AdrCategory": get_val("UDX.EDXF.TRANSPORT_CATEGORY", UDX),
            "NetWeightHazardousSubstances": get_val("UDX.EDXF.NET_WEIGHT_OF_HAZARDOUS_SUBSTANCE", UDX),
            "VolumeHazardousSubstances": get_val("UDX.EDXF.VOLUME_OF_HAZARDOUS_SUBSTANCES", UDX),
            "UnShippingName": [],
            "PackingGroup": get_val("UDX.EDXF.PACKING_GROUP", UDX),
            "LimitedQuantities": get_val("UDX.EDXF.LIMITED_QUANTITIES", UDX, val_type=bool),
            "ExceptedQuantities": get_val("UDX.EDXF.EXCEPTED_QUANTITIES", UDX, val_type=bool),
            "AggregationState": get_val("UDX.EDXF.AGGREGATION_STATE", UDX),
            "SpecialProvisionId": [get_val("UDX.EDXF.SPECIAL_PROVISION_ID", UDX)],
            "ClassificationCode": get_val("UDX.EDXF.CLASSIFICATION_CODE", UDX),
            "HazardLabel": [get_val("UDX.EDXF.HAZARD_LABEL", UDX)],
            "EnvironmentalHazards": get_val("UDX.EDXF.ENVIRONMENTAL_HAZARDS", UDX, val_type=bool),
            "TunnelCode": get_val("UDX.EDXF.TUNNEL_CODE", UDX),
            "LabelCode": [get_val("UDX.EDXF.GHS_LABEL_CODE", UDX)],
            "SignalWord": get_val("UDX.EDXF.GHS_SIGNAL_WORD", UDX),
            "HazardStatement": [get_val("UDX.EDXF.HAZARD_STATEMENT", UDX)],
            "PrecautionaryStatement": [get_val("UDX.EDXF.PRECAUTIONARY_STATEMENT", UDX)],
            "LiIonTested": get_val("UDX.EDXF.LI-ION_TESTED", UDX, val_type=bool),
            "LithiumAmount": get_val("UDX.EDXF.LITHIUM_AMOUNT", UDX),
            "BatteryEnergy": get_val("UDX.EDXF.BATTERY_ENERGY", UDX),
            "Nos274": get_val("UDX.EDXF.NOS_274", UDX, val_type=bool),
            "HazardTrigger": [get_val("UDX.EDXF.HAZARD_TRIGGER", UDX)]
        }
        append_multilingual_elements(UDX, ".//UDX.EDXF.SHIPPING_NAME",
            Legislation["UnShippingName"], "UnShippingName")
        Product["Legislation"].update(Legislation)            
        

        for PRODUCT_MIME in UDX.iterfind(".//UDX.EDXF.MIME"):
                ProductAttachments = {
                    "AttachmentType": map_attachment_type(get_val("UDX.EDXF.MIME_CODE", PRODUCT_MIME))or "ATX099", # Mandatory
                    #"ProductImageSimilar": "",
                    "AttachmentOrder": get_val("UDX.EDXF.MIME_ORDER", PRODUCT_MIME, val_type=int),
                    "AttachmentDetails": [{
                        "AttachmentLanguage": [convert_to_language_region_code(
                            PRODUCT_MIME.find("UDX.EDXF.MIME_SOURCE").get("lang", None))
                                               or DefaultLangxChange], # Mendatory if many languages !!!
                        #"AttachmentTypeSpecification": "",
                        "AttachmentFilename": get_val("UDX.EDXF.MIME_FILENAME", PRODUCT_MIME),
                        "AttachmentUri": get_val("UDX.EDXF.MIME_SOURCE", PRODUCT_MIME),
                        "AttachmentDescription": [],
                        "AttachmentIssueDate": get_val("UDX.EDXF.MIME_ISSUE_DATE", PRODUCT_MIME),
                        "AttachmentExpiryDate": get_val("UDX.EDXF.MIME_EXPIRY_DATE", PRODUCT_MIME)
                    }]
                }
                append_multilingual_elements(PRODUCT_MIME, "UDX.EDXF.MIME_DESIGNATION",
                    ProductAttachments["AttachmentDetails"][0]["AttachmentDescription"], "AttachmentDescription")
                Product["ProductAttachments"].append(ProductAttachments)

        if BMECAT_PRODUCT.find(".//MIME") is not None: # Specially for some ABB catalogs
            for PRODUCT_MIME_2 in BMECAT_PRODUCT.iterfind(".//MIME"):
                    ProductAttachments = {
                        "AttachmentType": map_attachment_type(get_val("MIME_CODE", PRODUCT_MIME_2) or get_val("MIME_DESCR", PRODUCT_MIME_2)) or "ATX099", # Mandatory
                        #"ProductImageSimilar": "",
                        "AttachmentOrder": get_val("MIME_ORDER", PRODUCT_MIME_2, val_type=int),
                        "AttachmentDetails": [{
                            "AttachmentLanguage": [convert_to_language_region_code(
                                PRODUCT_MIME_2.find("MIME_SOURCE").get("lang", None))
                                                or DefaultLangxChange], # Mendatory if many languages !!!
                            #"AttachmentTypeSpecification": "",
                            "AttachmentFilename": get_val("MIME_FILENAME", PRODUCT_MIME_2),
                            "AttachmentUri": get_val("MIME_SOURCE", PRODUCT_MIME_2),
                            "AttachmentDescription": [],
                            "AttachmentIssueDate": get_val("MIME_ISSUE_DATE", PRODUCT_MIME_2),
                            "AttachmentExpiryDate": get_val("MIME_EXPIRY_DATE", PRODUCT_MIME_2)
                        }]
                    }
                    append_multilingual_elements(PRODUCT_MIME_2, "UDX.EDXF.MIME_DESIGNATION",
                        ProductAttachments["AttachmentDetails"][0]["AttachmentDescription"], "AttachmentDescription")
                    Product["ProductAttachments"].append(ProductAttachments)


        for PRODUCT_FEATURES in BMECAT_PRODUCT.iterfind("./PRODUCT_FEATURES"):               
                EtimClassification = {
                    "EtimReleaseVersion": extract_etim_version(get_val("REFERENCE_FEATURE_SYSTEM_NAME", PRODUCT_FEATURES)), # Mandatory
                    "EtimClassCode": extract_class_code(get_val("REFERENCE_FEATURE_GROUP_ID", PRODUCT_FEATURES)), # Mandatory
                    #"EtimClassVersion": "",
                    "EtimDynamicReleaseDate": get_val("UDX.EDXF.PRODUCT_ETIM_RELEASE_DATE", UDX),
                    "EtimFeatures": [],
                    "EtimModellingClassCode": get_val("UDX.EDXF.REFERENCE_FEATURE_MC_ID", UDX),
                    "EtimModellingClassVersion": get_val("UDX.EDXF.REFERENCE_FEATURE_MC_VERSION", UDX, val_type=int),
                    "EtimModellingPorts": []
                }
                
                for FEATURE in PRODUCT_FEATURES.iterfind("./FEATURE"):
                    EtimFeatures = {
                        "EtimFeatureCode": get_val("FNAME", FEATURE), # Mandatory
                        
                        "EtimValueDetails": [],
                        "ReasonNoValue": get_val("FVALUE_DETAILS", FEATURE)
                    }
                    EtimFeatures.update(process_feature_values(FEATURE))
                    
                    append_multilingual_elements(FEATURE, ".//FVALUE_DETAILS",
                        EtimFeatures["EtimValueDetails"], "EtimValueDetails")
                    
                    EtimClassification["EtimFeatures"].append(EtimFeatures)
                
                
                # UNIQUE port codes
                ModellingPorts = []
                if UDX.findtext(".//UDX.EDXF.PORTCODE") is not None:
                    for PORTCODE in UDX.iterfind(".//UDX.EDXF.PORTCODE"):
                        if PORTCODE.text and PORTCODE.text not in ModellingPorts:
                            ModellingPorts.append(PORTCODE.text)
                #print(ModellingPorts)
                
                for PortCode in ModellingPorts:
                    EtimModellingPort = {
                        "EtimModellingPortcode": int(PortCode) if PortCode.isdigit() else None,
                        #"EtimModellingConnectionTypeCode": get_val("UDX.EDXF.CONNECTION_TYPE_CODE", BMECAT_PRODUCT),
                        #"EtimModellingConnectionTypeVersion": get_val("UDX.EDXF.CONNECTION_TYPE_VERSION", BMECAT_PRODUCT, val_type=int),
                        "EtimModellingFeatures": []
                    }
                    
                    # Find all features for this port
                    for FEATURE_MC in UDX.iterfind(f".//UDX.EDXF.FEATURE_MC[UDX.EDXF.PORTCODE='{PortCode}']"):
                        EtimFeature = {
                            "EtimFeatureCode": get_val("UDX.EDXF.FNAME", FEATURE_MC),  # Mandatory
                            
                            "EtimValueCoordinateX": get_val("UDX.EDXF.COORDINATE_X", FEATURE_MC),
                            "EtimValueCoordinateY": get_val("UDX.EDXF.COORDINATE_Y", FEATURE_MC),
                            "EtimValueCoordinateZ": get_val("UDX.EDXF.COORDINATE_Z", FEATURE_MC)
                        }
                        
                        # Process feature values (EV codes, numeric values, etc.)
                        EtimFeature.update(process_feature_values(FEATURE_MC, feature_xpath="./UDX.EDXF.FVALUE"))
                        
                        # Add matrix values if they exist
                        source_val = get_val("UDX.EDXF.MATRIX_SOURCE_VALUE", FEATURE_MC)
                        result_val = get_val("UDX.EDXF.MATRIX_RESULT_VALUE", FEATURE_MC)
                        if source_val and result_val:
                            EtimFeature["EtimValueMatrix"] = [{
                                "EtimValueMatrixSource": source_val,
                                "EtimValueMatrixResult": result_val
                            }]
                        
                        EtimModellingPort["EtimModellingFeatures"].append(EtimFeature)
                    
                    EtimClassification["EtimModellingPorts"].append(EtimModellingPort)             
       
       
                Product["EtimClassification"].append(EtimClassification)
        
        
        OtherClassifications = {
            "ClassificationName": "FUNIT" if get_val("FUNIT", BMECAT_PRODUCT) else "", # WIP
            #"ClassificationVersion": "",
            "ClassificationClassCode": get_val("FUNIT", BMECAT_PRODUCT), # WIP
            "ClassificationFeatures": [{
                "ClassificationFeatureName": "FUNIT" if get_val("FUNIT", BMECAT_PRODUCT) else "", # WIP
                "ClassificationFeatureValue1": get_val("FUNIT", BMECAT_PRODUCT), # WIP
                #"ClassificationFeatureValue2": "",
                "ClassificationFeatureUnit": get_val("FUNIT", BMECAT_PRODUCT)
            }]
        }
        Product["OtherClassifications"].append(OtherClassifications) 
        
        for PRODUCT_CHARACTERISTIC in UDX.iterfind(".//UDX.EDXF.PRODUCT_CHARACTERISTIC"):
                ProductCountrySpecificFields = {
                    "CSProductCharacteristicCode": get_val("UDX.EDXF.PRODUCT_CHARACTERISTIC_CODE", PRODUCT_CHARACTERISTIC),
                    "CSProductCharacteristicName": [],
                    "CSProductCharacteristicValueBoolean": get_val("UDX.EDXF.PRODUCT_CHARACTERISTIC_VALUE_BOOLEAN", PRODUCT_CHARACTERISTIC, val_type=bool),
                    "CSProductCharacteristicValueNumeric": get_val("UDX.EDXF.PRODUCT_CHARACTERISTIC_VALUE_NUMERIC", PRODUCT_CHARACTERISTIC),
                    "CSProductCharacteristicValueRangeLower": get_val("UDX.EDXF.PRODUCT_CHARACTERISTIC_VALUE_RANGE_FROM", PRODUCT_CHARACTERISTIC),
                    "CSProductCharacteristicValueRangeUpper": get_val("UDX.EDXF.PRODUCT_CHARACTERISTIC_VALUE_RANGE_TO", PRODUCT_CHARACTERISTIC),
                    "CSProductCharacteristicValueString": [],
                    "CSProductCharacteristicValueSet": [],
                    "CSProductCharacteristicValueSelect": get_val("UDX.EDXF.PRODUCT_CHARACTERISTIC_VALUE_SELECT", PRODUCT_CHARACTERISTIC),
                    "CSProductCharacteristicValueUnitCode": get_val("UDX.EDXF.PRODUCT_CHARACTERISTIC_VALUE_UNIT_CODE", PRODUCT_CHARACTERISTIC),
                    "CSProductCharacteristicReferenceGtin": get_val("UDX.EDXF.PRODUCT_CHARACTERISTIC_REFERENCE_GTIN", PRODUCT_CHARACTERISTIC)
                }
                
                append_multilingual_elements(PRODUCT_CHARACTERISTIC, ".//UDX.EDXF.PRODUCT_CHARACTERISTIC_NAME",
                    ProductCountrySpecificFields["CSProductCharacteristicName"], "CSProductCharacteristicName")
                
                append_multilingual_elements(PRODUCT_CHARACTERISTIC, ".//UDX.EDXF.PRODUCT_CHARACTERISTIC_VALUE_STRING",
                    ProductCountrySpecificFields["CSProductCharacteristicValueString"], "CSProductCharacteristicValueString")
                
                append_multilingual_elements(PRODUCT_CHARACTERISTIC, ".//UDX.EDXF.PRODUCT_CHARACTERISTIC_VALUE_SET",
                    ProductCountrySpecificFields["CSProductCharacteristicValueSet"], "CSProductCharacteristicValueSet")
                
                Product["ProductCountrySpecificFields"].append(ProductCountrySpecificFields) 
        
        
        TradeItem = {
            "ItemIdentification": {
                "SupplierItemNumber": get_val("SUPPLIER_PID", BMECAT_PRODUCT),
                "SupplierAltItemNumber": get_val("SUPPLIER_ALT_PID", BMECAT_PRODUCT),
                # "ManufacturerItemNumber": "",
                "ItemGtin": [get_val_attr("INTERNATIONAL_PID", BMECAT_PRODUCT, type="gtin")],
                "BuyerItemNumber": get_val_attr("BUYER_PID", BMECAT_PRODUCT, type="buyer_specific"),
                "DiscountGroupId": get_val("UDX.EDXF.DISCOUNT_GROUP_SUPPLIER", UDX),
                #"DiscountGroupDescription": 
                "BonusGroupId": get_val("UDX.EDXF.BONUS_GROUP_SUPPLIER", UDX)
                #"BonusGroupDescription": 
                #"ItemValidityDate": 
                #"ItemObsolescenceDate":
            },
            "ItemDetails": {
                #"ItemStatus": "",
                "ItemCondition": (BMECAT_PRODUCT.xpath(".//PRODUCT_STATUS/@type")[0].upper()
                    if BMECAT_PRODUCT.xpath(".//PRODUCT_STATUS/@type") and
                       BMECAT_PRODUCT.xpath(".//PRODUCT_STATUS/@type")[0].lower() in ["new", "refurbished", "used"]
                    else None),
                "StockItem": get_val("UDX.EDXF.PRODUCT_TO_STOCK", UDX, val_type=bool),
                "ShelfLifePeriod": get_val("UDX.EDXF.SHELF_LIFE_PERIOD", UDX, val_type=int),
                "ItemDescriptions": [{
                    "MinimalItemDescription": get_val_attr("UDX.EDXF.DESCRIPTION_VERY_SHORT", UDX)
                        or get_val_attr("DESCRIPTION_SHORT", BMECAT_PRODUCT),
                }]
            },
            "ItemRelations": [],
            "ItemLogisticDetails": [],
            "Ordering": {
                "OrderUnit": get_val("ORDER_UNIT", BMECAT_PRODUCT),
                "MinimumOrderQuantity": get_val("QUANTITY_MIN", BMECAT_PRODUCT),
                "OrderStepSize": get_val("QUANTITY_INTERVAL", BMECAT_PRODUCT),
                "StandardOrderLeadTime": get_val("DELIVERY_TIME", BMECAT_PRODUCT, val_type=int),
                "UseUnit": get_val("CONTENT_UNIT", BMECAT_PRODUCT),
                "UseUnitConversionFactor": get_val("NO_CU_PER_OU", BMECAT_PRODUCT),
                #"SingleUseUnitQuantity": get_val("ORDER_UNIT", BMECAT_PRODUCT),
                #"AlternativeUseUnit": get_val("ORDER_UNIT", BMECAT_PRODUCT),
                #"AlternativeUseUnitConversionFactor": get_val("ORDER_UNIT", BMECAT_PRODUCT),
            },
            "Pricing": [],
            "ItemAttachments": [],
            "ItemCountrySpecificFields": [],
            #"ItemCountrySpecificExtensions": [],
            "PackagingUnit": []
        }
          
        for ITEM_REFERENCE in BMECAT_PRODUCT.iterfind("./PRODUCT_REFERENCE"): 
            TradeItem["ItemRelations"].append({
                "RelatedSupplierItemNumber": get_val("PROD_ID_TO", ITEM_REFERENCE),
                #"RelatedManufacturerItemNumber": [],
                #"RelatedItemGtin": [],
                "RelationType": map_relation_type(ITEM_REFERENCE.xpath("@type")[0]) if ITEM_REFERENCE.xpath("@type") else "OTHER",
                "RelatedItemQuantity": int(ITEM_REFERENCE.xpath("@quantity")[0]) if ITEM_REFERENCE.xpath("@quantity") else 1
            })       
        
        ItemLogisticDetails = {
            "BaseItemNetLength": get_val("UDX.EDXF.NETLENGTH", UDX),
            "BaseItemNetWidth": get_val("UDX.EDXF.NETWIDTH", UDX),
            "BaseItemNetHeight": get_val("UDX.EDXF.NETDEPTH", UDX),
            "BaseItemNetDiameter": get_val("UDX.EDXF.NETDIAMETER", UDX),
            #"NetDimensionUnit": "",
            "BaseItemNetWeight": get_val("UDX.EDXF.NETWEIGHT", UDX),
            #"NetWeightUnit":
            "BaseItemNetVolume": get_val("UDX.EDXF.NETVOLUME", UDX),
            #"NetVolumeUnit": 
        }
        TradeItem["ItemLogisticDetails"].append(ItemLogisticDetails)
        
        Pricing = {
            "PriceUnit": get_val("PRICE_UNIT", BMECAT_PRODUCT) or get_val("ORDER_UNIT", BMECAT_PRODUCT),
            "PriceUnitFactor": get_val("PRICE_UNIT_FACTOR", BMECAT_PRODUCT),
            "PriceQuantity": get_val("PRICE_QUANTITY", BMECAT_PRODUCT),
            "PriceOnRequest": get_val("DAILY_PRICE", BMECAT_PRODUCT, val_type=bool),
            "GrossListPrice": next(iter(BMECAT_PRODUCT.xpath('.//PRODUCT_PRICE[@price_type="net_list"]/PRICE_AMOUNT/text()')), None),
            "NetPrice": next(iter(BMECAT_PRODUCT.xpath('.//PRODUCT_PRICE[@price_type="net_customer"]/PRICE_AMOUNT/text()')), None),
            "RecommendedRetailPrice": next(iter(BMECAT_PRODUCT.xpath('.//PRODUCT_PRICE[@price_type="nrp"]/PRICE_AMOUNT/text()')), None),
            "Vat": get_val("TAX", BMECAT_PRODUCT),
            "PriceValidityDate": next(iter(BMECAT_PRODUCT.xpath('.//DATETIME[@type="valid_start_date"]/DATE/text()')), None),
            "PriceExpiryDate": next(iter(BMECAT_PRODUCT.xpath('.//DATETIME[@type="valid_end_date"]/DATE/text()')), None)
            #"AllowanceSurcharge" : []

        }
        TradeItem["Pricing"].append(Pricing)
        
        for ITEM_MIME in UDX.iterfind(".//UDX.EDXF.MIME"):
                ItemAttachments = {
                    "AttachmentType": map_attachment_type(get_val("UDX.EDXF.MIME_CODE", ITEM_MIME))  or "ATX099", # Mandatory
                    "AttachmentDetails": [{
                        #"AttachmentLanguage": "",
                        #"AttachmentTypeSpecification": "",
                        "AttachmentFilename": get_val("UDX.EDXF.MIME_FILENAME", ITEM_MIME),
                        "AttachmentUri": get_val("UDX.EDXF.MIME_SOURCE", ITEM_MIME),
                        "AttachmentDescription": [],
                        "AttachmentIssueDate": get_val("UDX.EDXF.MIME_ISSUE_DATE", ITEM_MIME),
                        "AttachmentExpiryDate": get_val("UDX.EDXF.MIME_EXPIRY_DATE", ITEM_MIME)
                    }]
                }
                append_multilingual_elements(ITEM_MIME, "UDX.EDXF.MIME_DESIGNATION",
                    ItemAttachments["AttachmentDetails"][0]["AttachmentDescription"], "AttachmentDescription")
                TradeItem["ItemAttachments"].append(ItemAttachments)
        
        for ITEM_CHARACTERISTIC in UDX.iterfind(".//UDX.EDXF.PRODUCT_CHARACTERISTIC"):
                ProductCountrySpecificFields = {
                    "CSProductCharacteristicCode": get_val("UDX.EDXF.PRODUCT_CHARACTERISTIC_CODE", ITEM_CHARACTERISTIC),
                    "CSProductCharacteristicName": [],
                    "CSProductCharacteristicValueBoolean": get_val("UDX.EDXF.PRODUCT_CHARACTERISTIC_VALUE_BOOLEAN", ITEM_CHARACTERISTIC, val_type=bool),
                    "CSProductCharacteristicValueNumeric": get_val("UDX.EDXF.PRODUCT_CHARACTERISTIC_VALUE_NUMERIC", ITEM_CHARACTERISTIC),
                    "CSProductCharacteristicValueRangeLower": get_val("UDX.EDXF.PRODUCT_CHARACTERISTIC_VALUE_RANGE_FROM", ITEM_CHARACTERISTIC),
                    "CSProductCharacteristicValueRangeUpper": get_val("UDX.EDXF.PRODUCT_CHARACTERISTIC_VALUE_RANGE_TO", ITEM_CHARACTERISTIC),
                    "CSProductCharacteristicValueString": [],
                    "CSProductCharacteristicValueSet": [],
                    "CSProductCharacteristicValueSelect": get_val("UDX.EDXF.PRODUCT_CHARACTERISTIC_VALUE_SELECT", ITEM_CHARACTERISTIC),
                    "CSProductCharacteristicValueUnitCode": get_val("UDX.EDXF.PRODUCT_CHARACTERISTIC_VALUE_UNIT_CODE", ITEM_CHARACTERISTIC),
                    "CSProductCharacteristicReferenceGtin": get_val("UDX.EDXF.PRODUCT_CHARACTERISTIC_REFERENCE_GTIN", ITEM_CHARACTERISTIC)
                }
                
                append_multilingual_elements(PRODUCT_CHARACTERISTIC, ".//UDX.EDXF.PRODUCT_CHARACTERISTIC_NAME",
                    ProductCountrySpecificFields["CSProductCharacteristicName"], "CSProductCharacteristicName")
                
                append_multilingual_elements(PRODUCT_CHARACTERISTIC, ".//UDX.EDXF.PRODUCT_CHARACTERISTIC_VALUE_STRING",
                    ProductCountrySpecificFields["CSProductCharacteristicValueString"], "CSProductCharacteristicValueString")
                
                append_multilingual_elements(PRODUCT_CHARACTERISTIC, ".//UDX.EDXF.PRODUCT_CHARACTERISTIC_VALUE_SET",
                    ProductCountrySpecificFields["CSProductCharacteristicValueSet"], "CSProductCharacteristicValueSet")
                
                Product["ProductCountrySpecificFields"].append(ProductCountrySpecificFields) 
        
        for PACKING_UNIT in UDX.iterfind(".//UDX.EDXF.PACKING_UNIT"): 
            TradeItem["PackagingUnit"].append({
                "PackagingIdentification": {
                    #SupplierPackagingNumber
                    #ManufacturerPackagingNumber
                    "PackagingGtin": [get_val("UDX.EDXF.GTIN", PACKING_UNIT)],
                    "PackagingTypeCode": get_val("UDX.EDXF.PACKING_UNIT_CODE", PACKING_UNIT),
                    "PackagingQuantity": get_val("UDX.EDXF.QUANTITY_MAX", PACKING_UNIT),
                    #TradeItemPrimaryPackaging
                    "PackagingGs1Code128": get_val("UDX.EDXF.GS1_128", PACKING_UNIT),
                    #PackagingRecyclable
                    #PackagingReusable
                    "PackagingBreak": get_val("UDX.EDXF.PACKAGE_BREAK", PACKING_UNIT, val_type=bool),
                    "NumberOfPackagingParts": get_val("UDX.EDXF.PACKING_PARTS", PACKING_UNIT, val_type=int), 
                },
                "PackagingLogisticDetails": [{
                    #SupplierPackagingPartNumber
                    #ManufacturerPackagingPartNumber
                    #PackagingPartGtin
                    "PackagingTypeLength": get_val("UDX.EDXF.LENGTH", PACKING_UNIT),
                    "PackagingTypeWidth": get_val("UDX.EDXF.WIDTH", PACKING_UNIT),
                    "PackagingTypeHeight": get_val("UDX.EDXF.DEPTH", PACKING_UNIT),
                    "PackagingTypeDiameter": get_val("UDX.EDXF.DIAMETER", PACKING_UNIT),
                    #PackagingTypeDimensionUnit
                    "PackagingTypeWeight": get_val("UDX.EDXF.WEIGHT", PACKING_UNIT),
                    #PackagingTypeWeightUnit
                    #PackagingStackable
                }]
            })   
        
        Product["TradeItem"].append(TradeItem) 
        

        xChange["Supplier"][0]["Product"].append(Product)
        #Supplier["Product"].append(Product)
        
        #BMECAT_PRODUCT.clear()
     
        
    #xChange["Supplier"].append(Supplier)  
    
    print(f"Finished processing {product_counter} products")
    root.clear()
    return xChange

def clean_json(data):
    """
    Recursively clean a JSON-compatible Python object by removing all empty values.
    Empty values are: None, empty strings, empty lists, and empty dictionaries.
    
    Args:
        data: Any JSON-compatible Python object (dict, list, str, int, float, bool, None)
        
    Returns:
        A cleaned version of the input data with empty values removed
    """
    # Early return for primitives
    if not isinstance(data, (dict, list)):
        return data
    
    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            cleaned_value = clean_json(value)
            # Check if cleaned value is empty
            if cleaned_value is not None and cleaned_value != "" and cleaned_value != [] and cleaned_value != {}:
                result[key] = cleaned_value
        return result
    else:  # must be a list
        result = []
        for item in data:
            cleaned_item = clean_json(item)
            # Check if cleaned item is empty
            if cleaned_item is not None and cleaned_item != "" and cleaned_item != [] and cleaned_item != {}:
                result.append(cleaned_item)
        return result


def load_json_file(file_path):
    try:
        with open(file_path, "rb") as file:  # Note: orjson requires binary mode
            data = orjson.loads(file.read())
            return data
    except FileNotFoundError:
        raise SystemExit(f"Error: File '{file_path}' not found.")
    except orjson.JSONDecodeError as e:
        raise SystemExit(f"Invalid JSON in '{file_path}': {e}")
    except Exception as e:
        raise SystemExit(f"Error reading file '{file_path}': {e}")

def validate_json(instance_path, schema_path):
    # Load instance and schema data
    instance_data = load_json_file(instance_path)
    schema_data = load_json_file(schema_path)

    try:
        # Create validator (schema validation happens here)
        validator = jsonschema_rs.validator_for(schema_data)
    except Exception as e:
        raise SystemExit(f"Invalid schema: {e}")

    # Perform validation
    try:
        validator.validate(instance_data)
        print(f"{instance_path} is valid against schema {schema_path}")
    except jsonschema_rs.ValidationError as e:
        for error in validator.iter_errors(instance_data):
            print(f"Error: {error.message}")
            print(f"Location: {error.instance_path}")
            print(f"Location in schema: {error.schema_path}\n")
    except Exception as e:
        raise SystemExit(f"Error during validation: {e}")



def convert_file(input_path: str, output_path: str) -> None:

    print(f"Working with: {input_path}")

    xChange = convert_BMEcat(input_path)

    print("Cleaning JSON...")
    xChange_cleaned = clean_json(xChange)
    del xChange

    print("Writing JSON...")
    with open(output_path, "wb") as file:
        file.write(orjson.dumps(xChange_cleaned,
                                option=orjson.OPT_INDENT_2))
    del xChange_cleaned

    print(f"Conversion completed: {output_path}")
    
    print("Validating JSON...")
    validate_json(output_path, "xChange_Schema_V1.1-2024-08-23.json")
    
    print(f"Processing completed successfully: {output_path}")
