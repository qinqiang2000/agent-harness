<?xml version="1.0" encoding="UTF-8"?>
<xsl:transform xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
               xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
               xmlns:ubl="urn:oasis:names:specification:ubl:schema:xsd:Order-2"
               xmlns:xs="http://www.w3.org/2001/XMLSchema"
               xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
               xmlns:svrl="http://purl.oclc.org/dsdl/svrl"
               version="2.0">

	<!-- Import common validation templates -->
	<xsl:import href="../common/KDUBL-common-validation.xslt"/>

	<xsl:output method="xml" indent="yes" encoding="UTF-8"/>

	<!-- Main template -->
	<xsl:template match="/">
		<svrl:schematron-output title="KDUBL 2.1 OrderOnly Validation Rules" schemaVersion="iso">
			<svrl:ns-prefix-in-attribute-values uri="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2" prefix="cbc"/>
			<svrl:ns-prefix-in-attribute-values uri="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2" prefix="cac"/>
			<svrl:ns-prefix-in-attribute-values uri="urn:oasis:names:specification:ubl:schema:xsd:Order-2" prefix="ubl"/>

			<svrl:active-pattern id="KDUBL-order-only-patterns" name="KDUBL-order-only-patterns"/>
			<xsl:apply-templates select="/" mode="M1"/>
		</svrl:schematron-output>
	</xsl:template>

	<!-- Mode M1: Document level validation -->
	<xsl:template match="ubl:Order" priority="1000" mode="M1">
		<svrl:fired-rule context="ubl:Order"/>

		<!-- Call common validation templates -->
		<xsl:call-template name="validate-customization-id">
			<xsl:with-param name="context" select="."/>
		</xsl:call-template>

		<xsl:call-template name="validate-profile-id">
			<xsl:with-param name="context" select="."/>
		</xsl:call-template>

		<xsl:call-template name="validate-issue-date">
			<xsl:with-param name="context" select="."/>
		</xsl:call-template>

		<xsl:call-template name="validate-issue-time">
			<xsl:with-param name="context" select="."/>
		</xsl:call-template>

		<!-- OrderOnly-specific validation rules can be added here in the future -->
	</xsl:template>

	<!-- Default templates -->
	<xsl:template match="text() | @*" mode="#all" priority="-10"/>
	<xsl:template match="*" mode="M1" priority="-10">
		<xsl:apply-templates select="*" mode="M1"/>
	</xsl:template>

</xsl:transform>
