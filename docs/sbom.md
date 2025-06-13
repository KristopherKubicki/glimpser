# Software Bill of Materials

The build workflow produces a CycloneDX Software Bill of Materials using
`cyclonedx-bom`. The SBOM is generated automatically in the
`dependency-check` job and uploaded as an artefact. Include it when creating
releases so consumers can audit the dependencies shipped with Glimpser.
