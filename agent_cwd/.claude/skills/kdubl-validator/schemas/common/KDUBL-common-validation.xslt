<?xml version="1.0" encoding="UTF-8"?>
<xsl:transform xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
               xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
               xmlns:xs="http://www.w3.org/2001/XMLSchema"
               xmlns:svrl="http://purl.oclc.org/dsdl/svrl"
               version="2.0">

	<!-- Named template: CustomizationID validation -->
	<xsl:template name="validate-customization-id">
		<xsl:param name="context" select="."/>
		<xsl:param name="expected-value" select="''"/>

		<!-- KDUBL-R-CUSTOM-001: CustomizationID is mandatory -->
		<xsl:choose>
			<xsl:when test="$context/cbc:CustomizationID and normalize-space($context/cbc:CustomizationID) != ''"/>
			<xsl:otherwise>
				<svrl:failed-assert test="cbc:CustomizationID and normalize-space(cbc:CustomizationID) != ''" flag="fatal" id="KDUBL-R-CUSTOM-001">
					<xsl:attribute name="location">
						<xsl:apply-templates select="$context" mode="schematron-select-full-path"/>
					</xsl:attribute>
					<svrl:text>[KDUBL-R-CUSTOM-001] CustomizationID (cbc:CustomizationID) is mandatory.</svrl:text>
				</svrl:failed-assert>
			</xsl:otherwise>
		</xsl:choose>

		<!-- KDUBL-R-CUSTOM-002: CustomizationID value must match expected value (if provided) -->
		<xsl:if test="$expected-value != '' and $context/cbc:CustomizationID and normalize-space($context/cbc:CustomizationID) != ''">
			<xsl:if test="normalize-space($context/cbc:CustomizationID) != $expected-value">
				<svrl:failed-assert test="normalize-space(cbc:CustomizationID) = $expected-value" flag="fatal" id="KDUBL-R-CUSTOM-002">
					<xsl:attribute name="location">
						<xsl:apply-templates select="$context" mode="schematron-select-full-path"/>
					</xsl:attribute>
					<svrl:text>[KDUBL-R-CUSTOM-002] CustomizationID value must be "<xsl:value-of select="$expected-value"/>", but found "<xsl:value-of select="normalize-space($context/cbc:CustomizationID)"/>".</svrl:text>
				</svrl:failed-assert>
			</xsl:if>
		</xsl:if>
	</xsl:template>

	<!-- Named template: ProfileID validation -->
	<xsl:template name="validate-profile-id">
		<xsl:param name="context" select="."/>
		<xsl:param name="expected-value" select="''"/>

		<!-- KDUBL-R-PROFILE-001: ProfileID is mandatory -->
		<xsl:choose>
			<xsl:when test="$context/cbc:ProfileID and normalize-space($context/cbc:ProfileID) != ''"/>
			<xsl:otherwise>
				<svrl:failed-assert test="cbc:ProfileID and normalize-space(cbc:ProfileID) != ''" flag="fatal" id="KDUBL-R-PROFILE-001">
					<xsl:attribute name="location">
						<xsl:apply-templates select="$context" mode="schematron-select-full-path"/>
					</xsl:attribute>
					<svrl:text>[KDUBL-R-PROFILE-001] ProfileID (cbc:ProfileID) is mandatory.</svrl:text>
				</svrl:failed-assert>
			</xsl:otherwise>
		</xsl:choose>

		<!-- KDUBL-R-PROFILE-002: ProfileID value must match expected value (if provided) -->
		<xsl:if test="$expected-value != '' and $context/cbc:ProfileID and normalize-space($context/cbc:ProfileID) != ''">
			<xsl:if test="normalize-space($context/cbc:ProfileID) != $expected-value">
				<svrl:failed-assert test="normalize-space(cbc:ProfileID) = $expected-value" flag="fatal" id="KDUBL-R-PROFILE-002">
					<xsl:attribute name="location">
						<xsl:apply-templates select="$context" mode="schematron-select-full-path"/>
					</xsl:attribute>
					<svrl:text>[KDUBL-R-PROFILE-002] ProfileID value must be "<xsl:value-of select="$expected-value"/>", but found "<xsl:value-of select="normalize-space($context/cbc:ProfileID)"/>".</svrl:text>
				</svrl:failed-assert>
			</xsl:if>
		</xsl:if>
	</xsl:template>

	<!-- Named template: IssueDate validation -->
	<xsl:template name="validate-issue-date">
		<xsl:param name="context" select="."/>

		<!-- KDUBL-R-002: IssueDate is optional, only validate format if present -->

		<!-- KDUBL-R-002b: IssueDate format must be YYYY-MM-DD (if provided) -->
		<xsl:if test="$context/cbc:IssueDate and normalize-space($context/cbc:IssueDate) != ''">
			<xsl:variable name="issueDateValue" select="normalize-space($context/cbc:IssueDate)"/>
			<xsl:choose>
				<xsl:when test="string-length($issueDateValue) = 10 and matches($issueDateValue, '^\d{4}-\d{2}-\d{2}$') and ($issueDateValue castable as xs:date)"/>
				<xsl:otherwise>
					<svrl:failed-assert test="string-length(normalize-space(cbc:IssueDate)) = 10 and matches(normalize-space(cbc:IssueDate), '^\d{4}-\d{2}-\d{2}$') and (normalize-space(cbc:IssueDate) castable as xs:date)" flag="fatal" id="KDUBL-R-002b">
						<xsl:attribute name="location">
							<xsl:apply-templates select="$context" mode="schematron-select-full-path"/>
						</xsl:attribute>
						<svrl:text>[KDUBL-R-002b] Invoice issue date (cbc:IssueDate) must be formatted as YYYY-MM-DD (e.g., 2025-12-31), but found "<xsl:value-of select="$issueDateValue"/>".</svrl:text>
					</svrl:failed-assert>
				</xsl:otherwise>
			</xsl:choose>
		</xsl:if>
	</xsl:template>

	<!-- Named template: IssueTime validation -->
	<xsl:template name="validate-issue-time">
		<xsl:param name="context" select="."/>

		<!-- KDUBL-R-002a: IssueTime is optional, only validate format if present -->

		<!-- KDUBL-R-002c: IssueTime format must be HH:MM:SS+/-HH:MM (if provided) -->
		<xsl:if test="$context/cbc:IssueTime and normalize-space($context/cbc:IssueTime) != ''">
			<xsl:variable name="issueTimeValue" select="normalize-space($context/cbc:IssueTime)"/>
			<xsl:choose>
				<xsl:when test="matches($issueTimeValue, '^\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$')"/>
				<xsl:otherwise>
					<svrl:failed-assert test="matches(normalize-space(cbc:IssueTime), '^\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$')" flag="fatal" id="KDUBL-R-002c">
						<xsl:attribute name="location">
							<xsl:apply-templates select="$context" mode="schematron-select-full-path"/>
						</xsl:attribute>
						<svrl:text>[KDUBL-R-002c] Invoice issue time (cbc:IssueTime) must include a timezone offset in HH:MM:SS+/-HH:MM format (e.g., 09:15:00+08:00). Found "<xsl:value-of select="$issueTimeValue"/>".</svrl:text>
					</svrl:failed-assert>
				</xsl:otherwise>
			</xsl:choose>
		</xsl:if>
	</xsl:template>

	<!-- Helper template: Generate element full path -->
	<xsl:template match="*" mode="schematron-select-full-path">
		<xsl:for-each select="ancestor-or-self::*">
			<xsl:text>/</xsl:text>
			<xsl:if test="namespace-uri() != ''">
				<xsl:value-of select="name()"/>
			</xsl:if>
			<xsl:if test="namespace-uri() = ''">
				<xsl:value-of select="local-name()"/>
			</xsl:if>
			<xsl:variable name="pCount" select="count(preceding-sibling::*[local-name() = local-name(current())])"/>
			<xsl:if test="$pCount &gt; 0">
				<xsl:text>[</xsl:text>
				<xsl:value-of select="$pCount + 1"/>
				<xsl:text>]</xsl:text>
			</xsl:if>
		</xsl:for-each>
	</xsl:template>

</xsl:transform>
