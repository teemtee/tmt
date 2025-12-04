
### Notes, contributors, tests

- [ ] Review the release notes content and update the text as needed
- [ ] Write release notes for any essential changes which were missed
- [ ] Verify the rendering locally using `make docs` or the `docs/readthedocs.org:tmt` GitHub action check
- [ ] Use `./scripts/list-new-contributors` to identify new contributors, update `docs/overview.rst` accordingly
- [ ] Commit and push all release notes and contributor changes
- [ ] Make sure that the full test coverage has been successfully executed
- [ ] Merge the release pull request

### Tag, release, downstream

- [ ] Make sure you have the release commit: `git checkout main && git pull`
- [ ] Tag the commit with `x.y.z`, push tags using `git push --tags`
- [ ] Create a new [github release](https://github.com/teemtee/tmt/releases/) based on the tag above
- [ ] Mention the most important changes in the release name, do not include version
- [ ] Push the “Generate release notes” button to create the content, publish the release
- [ ] Check Fedora [pull requests](https://src.fedoraproject.org/rpms/tmt/pull-requests) and review proposed changes
- [ ] Make sure that tests pass and merge individual pull requests

### Milestones, container images

- [ ] Use the bulk edit in the [milestone view](https://github.com/orgs/teemtee/projects/1/views/19) to set the milestone for all issues and pull requests included in the sprint
- [ ] Close the corresponding [release milestone](https://github.com/teemtee/tmt/milestones)
- [ ] Once the non development [copr build](https://copr.fedorainfracloud.org/coprs/g/teemtee/stable/builds/) is completed, run the [publish-images](https://github.com/teemtee/tmt/actions/workflows/publish-images.yml) workflow to build fresh container image.
