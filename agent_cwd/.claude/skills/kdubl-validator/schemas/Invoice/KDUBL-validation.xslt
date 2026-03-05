<?xml version="1.0" encoding="UTF-8"?>
<xsl:transform xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
               xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
               xmlns:ubl-invoice="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
               xmlns:xs="http://www.w3.org/2001/XMLSchema"
               xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
               xmlns:svrl="http://purl.oclc.org/dsdl/svrl"
               version="2.0">

	<!-- Import common validation templates -->
	<xsl:import href="../common/KDUBL-common-validation.xslt"/>

	<xsl:output method="xml" indent="yes" encoding="UTF-8"/>
	
	<!-- Main template -->
	<xsl:template match="/">
		<svrl:schematron-output title="KDUBL 2.1 Invoice Validation Rules" schemaVersion="iso">
			<svrl:ns-prefix-in-attribute-values uri="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2" prefix="cbc"/>
			<svrl:ns-prefix-in-attribute-values uri="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2" prefix="cac"/>
			<svrl:ns-prefix-in-attribute-values uri="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2" prefix="ubl-invoice"/>
			
			<svrl:active-pattern id="KDUBL-all-patterns" name="KDUBL-all-patterns"/>
			<xsl:apply-templates select="/" mode="M1"/>
		</svrl:schematron-output>
	</xsl:template>
	
	<!-- Mode M1: Document level validation - Phase 1: CustomizationID and ProfileID validation -->
	<xsl:template match="ubl-invoice:Invoice" priority="1000" mode="M1">
		<svrl:fired-rule context="ubl-invoice:Invoice"/>

		<!-- Call common validation templates -->
		<xsl:call-template name="validate-customization-id">
			<xsl:with-param name="context" select="."/>
			<xsl:with-param name="expected-value" select="'urn:piaozone.com:ubl-2.1-customizations:v1.0'"/>
		</xsl:call-template>

		<xsl:call-template name="validate-profile-id">
			<xsl:with-param name="context" select="."/>
			<xsl:with-param name="expected-value" select="'urn:piaozone.com:profile:bill:v1.0'"/>
		</xsl:call-template>

		<xsl:call-template name="validate-issue-date">
			<xsl:with-param name="context" select="."/>
		</xsl:call-template>

		<xsl:call-template name="validate-issue-time">
			<xsl:with-param name="context" select="."/>
		</xsl:call-template>

		<!-- KDUBL-R-TAX-001: 跨境发票文档级别必须有2个TaxTotal -->
		<xsl:if test="cbc:DocumentCurrencyCode and normalize-space(cbc:DocumentCurrencyCode) != ''
		           and cbc:TaxCurrencyCode and normalize-space(cbc:TaxCurrencyCode) != ''
		           and normalize-space(cbc:DocumentCurrencyCode) != normalize-space(cbc:TaxCurrencyCode)">
			<xsl:if test="count(cac:TaxTotal) != 2">
				<svrl:failed-assert test="count(cac:TaxTotal) = 2" flag="fatal" id="KDUBL-R-TAX-001">
					<xsl:attribute name="location">
						<xsl:apply-templates select="." mode="schematron-select-full-path"/>
					</xsl:attribute>
					<svrl:text>[KDUBL-R-TAX-001] When DocumentCurrencyCode ("<xsl:value-of select="normalize-space(cbc:DocumentCurrencyCode)"/>") differs from TaxCurrencyCode ("<xsl:value-of select="normalize-space(cbc:TaxCurrencyCode)"/>"), the invoice must have exactly 2 cac:TaxTotal elements at document level, but found <xsl:value-of select="count(cac:TaxTotal)"/>.</svrl:text>
				</svrl:failed-assert>
			</xsl:if>
		</xsl:if>

		<xsl:apply-templates select="*" mode="M1"/>
	</xsl:template>

	<!-- Mode M1: InvoiceLine level TaxTotal validation -->
	<xsl:template match="cac:InvoiceLine" priority="1000" mode="M1">
		<svrl:fired-rule context="cac:InvoiceLine"/>
		<xsl:variable name="docCurrency" select="normalize-space(ancestor::ubl-invoice:Invoice/cbc:DocumentCurrencyCode)"/>
		<xsl:variable name="taxCurrency" select="normalize-space(ancestor::ubl-invoice:Invoice/cbc:TaxCurrencyCode)"/>
		<xsl:if test="$docCurrency != '' and $taxCurrency != '' and $docCurrency != $taxCurrency">
			<xsl:if test="count(cac:TaxTotal) != 2">
				<svrl:failed-assert test="count(cac:TaxTotal) = 2" flag="fatal" id="KDUBL-R-TAX-002">
					<xsl:attribute name="location">
						<xsl:apply-templates select="." mode="schematron-select-full-path"/>
					</xsl:attribute>
					<svrl:text>[KDUBL-R-TAX-002] When DocumentCurrencyCode ("<xsl:value-of select="$docCurrency"/>") differs from TaxCurrencyCode ("<xsl:value-of select="$taxCurrency"/>"), each cac:InvoiceLine must have exactly 2 cac:TaxTotal elements, but found <xsl:value-of select="count(cac:TaxTotal)"/> in line <xsl:value-of select="cbc:ID"/>.</svrl:text>
				</svrl:failed-assert>
			</xsl:if>
		</xsl:if>
		<xsl:apply-templates select="*" mode="M1"/>
	</xsl:template>

	<!-- Default templates -->
	<xsl:template match="text() | @*" mode="#all" priority="-10"/>
	<xsl:template match="*" mode="M1" priority="-10">
		<xsl:apply-templates select="*" mode="M1"/>
	</xsl:template>

</xsl:transform>
