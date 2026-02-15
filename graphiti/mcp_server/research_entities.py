"""
Research Domain Entity Types for Graphiti

Custom entity types optimized for research/grants document corpus.
These guide LLM extraction to produce consistent, typed entities.

NOTE: Graphiti handles the entity 'name' separately during extraction.
These types define ADDITIONAL attributes to capture structured information.
"""

from pydantic import BaseModel, Field


class Project(BaseModel):
    """A funded research project, grant, or initiative.

    Instructions for identifying and extracting projects:
    1. Look for project names, acronyms (MICA, CODAP, DataTools), and grant titles
    2. Identify award numbers or grant identifiers when mentioned
    3. Pay attention to phrases like "the project", "this initiative", "our research"
    4. Extract the funding program (DRK-12, ITEST, AISL) when mentioned
    5. Identify the funding agency (NSF, DOE, NIH) when referenced
    6. Capture project duration or timeline if mentioned
    7. Note collaborating institutions or partners
    8. Always create edges connecting the project to its PI, Co-PIs, and organizations
    """

    funding_program: str | None = Field(
        None,
        description="Funding program if mentioned (e.g., 'DRK-12', 'ITEST', 'AISL', 'ECR')",
    )
    funder: str | None = Field(
        None,
        description="Funding agency if mentioned (e.g., 'NSF', 'Department of Education')",
    )
    description: str = Field(
        ...,
        description="Brief description of the project's goals, activities, and scope.",
    )


class Organization(BaseModel):
    """An institution, company, nonprofit, government agency, or funding body.

    Instructions for identifying and extracting organizations:
    1. Look for university names (full or abbreviated: UIUC, MIT, Stanford)
    2. Identify nonprofit organizations (Concord Consortium, TERC, WestEd)
    3. Recognize government agencies (NSF, NIH, Department of Education)
    4. Find companies or corporate partners
    5. Note research labs or centers within larger institutions
    6. Identify funding agencies and foundations (NSF, Spencer Foundation, Gates Foundation)
    7. Capture the organization type when evident
    8. Preserve common abbreviations alongside full names
    9. Create edges connecting organizations to people who work there
    10. Create edges connecting funding organizations to projects they fund
    """

    org_type: str | None = Field(
        None,
        description="Type: 'University', 'Nonprofit', 'Research Lab', 'Government Agency', 'Company', 'Funding Agency', 'Foundation'",
    )
    description: str = Field(
        ...,
        description="Brief description of the organization's role and involvement.",
    )


class Person(BaseModel):
    """A person mentioned in research documents.

    Instructions for identifying and extracting people:
    1. Look for full names, especially in context of roles or affiliations
    2. Identify role when mentioned: PI, Co-PI, Researcher, Developer, etc.
    3. Common roles in research documents:
       - Principal Investigator (PI) - leads the project
       - Co-Principal Investigator (Co-PI) - shares leadership
       - Researcher - conducts research activities
       - Software Developer - builds software/tools
       - Finance & Administration (F&A) - handles budgets, compliance
       - Program Officer - manages grants at funding agency
       - Evaluator - conducts project evaluation
       - Graduate Student / Postdoc - research trainees
    4. Capture institutional affiliation when mentioned
    5. Note expertise areas if described
    6. Always create edges connecting people to their projects and organizations
    7. Distinguish between project staff and external collaborators
    """

    role: str | None = Field(
        None,
        description="Role: 'PI', 'Co-PI', 'Researcher', 'Software Developer', 'F&A', 'Program Officer', 'Evaluator'",
    )
    affiliation: str | None = Field(
        None,
        description="Organization they belong to (e.g., 'Concord Consortium', 'UIUC')",
    )
    description: str = Field(
        ...,
        description="Brief description of the person's role and contributions.",
    )


class Software(BaseModel):
    """Software, tools, platforms, or technology.

    Instructions for identifying and extracting software:
    1. Look for named software products (CODAP, Common Online Data Analysis Platform)
    2. Identify development tools and platforms (Unity, React, Python)
    3. Recognize educational technology tools
    4. Find data analysis or visualization tools
    5. Note programming languages and frameworks
    6. Capture hardware/software combinations (HoloLens, VR systems)
    7. Distinguish between software being developed vs. software being used
    8. Create edges connecting software to projects that develop or use them
    """

    software_type: str | None = Field(
        None,
        description="Type: 'Educational Tool', 'Development Platform', 'Analysis Tool', 'Hardware', 'Framework'",
    )
    description: str = Field(
        ...,
        description="Brief description of what the software does and its purpose.",
    )


# Dictionary mapping entity type names to their Pydantic models
# This is used by Graphiti's entity extraction system
#
# Note: FundingProgram and Funder were removed (2026-02-15) and merged into
# Organization with org_type='Funding Agency'/'Foundation'. The pilot showed
# 0 FundingProgram and 1 Funder across 9 docs — too sparse to justify separate
# types. Funding info is also captured on Project (funding_program, funder fields).
# If needed later, these types can be re-added for a targeted re-extraction.
RESEARCH_ENTITY_TYPES: dict[str, type[BaseModel]] = {
    "Project": Project,
    "Organization": Organization,
    "Person": Person,
    "Software": Software,
}
