
### Prepare release notes, commit and tag

- [ ] Update overview.rst with new contributors since the last release
- [ ] Review the release notes in `docs/releases/pending`, update as needed
- [ ] Move release notes from `pending` to a versioned directory
- [ ] Add a Release x.y.z commit: `git commit "Release x.y.z"`
- [ ] Create a pull request with the commit, ensure tests pass, merge it
- [ ] Tag the commit with `x.y.z`, push tags using `git push --tags`

### Create a new github release

- [ ] Mention the most important changes in the name, do not include version
- [ ] Use ; as a delimiter, when multiple items are mentioned in the name
- [ ] Push the “Generate release notes” button to create the content
- [ ] Prepend the “See the release notes for the list of interesting changes.” line
- [ ] Publish the release
- [ ] Check Fedora pull requests, make sure tests pass and merge

### Milestones and container images

- [ ] Use the bulk edit in the [milestone view](https://github.com/orgs/teemtee/projects/1/views/19) to set the milestone for all issues and pull requests included in the sprint
- [ ] Close the corresponding [release milestone](https://github.com/teemtee/tmt/milestones)
- [ ] Once the non development [copr build](https://copr.fedorainfracloud.org/coprs/g/teemtee/stable/builds/) is completed, run the [publish-images](https://github.com/teemtee/tmt/actions/workflows/publish-images.yml) workflow to build fresh container image.

### Handle manually what did not go well

- [ ] If the automation triggered by publishing the new github release was not successful, publish the fresh code to the pypi repository manually using `hatch build && twine upload`
- [ ] If there was a problem with creating Fedora pull requests, you can trigger them manually using `/packit propose-downstream` in any open issue.
