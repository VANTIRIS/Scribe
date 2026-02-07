get rid of "Navigation
Left-drag: orbit
Right-drag: pan
Scroll: zoom
Click: select face"


move concols to the bototm of th left panel. 

use a more normal upload drag in aor click box fo rhteimport. 
Use a more normal download export buttom  
if we adjust the color of the selected face, the color should just be the surface color, not a blend of selected color and surface color. 
we should make the selected color glow slightly, or maybe color pulse subtlely. 


we should save to sqlite every time we make a metadata change. confirm in console that db was updated. 


we should show the uuid in the top right of the menu bar. 

write readme



if we select a different ssurface color, we did to temp disable the selected face color, just until we're done picking the color. 
add zoom off center to pan feature, like normal CAD programs normally use. 


add pin icons that expand and contrac the left and right panels.
move console to the bottom of the left panel 
grid off by default 
add 3 point lighting in the environment with a lighting button in the top of the menu bar


propogate the rest of the tolerance dropdown and dat and meta data portion to the panel and the meta data 
lets consider how to add a heat map option and a hole Id option. make a single html file with different visual options for me to choose the style. 
selected face pulse magnitutde should be less server and slightly faster 
make edges slightly 35% thicker 
we should have the baseurl/uuid be the page it loads to after the upload. 
update readme with all these new features 
justify the console log to the bottom of the left panel. 
simpify the export button area 
tweak lighting slighly, making it brighter and slightly different from each point 
make the xyz slightly smaller. add a little cube view over he xyz with clickable orthogonal faces that'll quick snap to a 90deg normal view. 
if we hold chisft or control which selecting a new face, it should select multiple faces. 
escape key to deselect all and cancel
do a commprehensive code check, audit, cleanup, and tidy. 

get rid of thread pitch box. this is served by the thread size. In thread type, make UNC first, then UNF, then metric course, then metric fine, then helicoil, then keensert
make the lighting button on the top of the bar actually a popup modal for the lighting options. We need to add some more shading, brighting, spotlight settings, strength, ect all the standatd stuff


when multiple faces were selected, both face colors weren't saved to db. only one was. it also failed to save the dimensioning meta data

make a expansion icon for the right side panel. 

we need a hole manage that expands as the right side panel. we need all the different idenified holes to pop up in this manager in an organized way.

we also need a heat map mode for tolerances.

the top back left cube needs to snap to the direction that's clicked on the cube face, raycast from mouse pointer 

right side panle needs to eb scrolling vetically.

add a tolerances button on the top meny bar that opens a modal with a list of all the tolerances in the model. 

we need a hole wizard button top bar that pops the right side panel in with the hole data


in heatmap mode, we need to color code the different types of tolerance callouts. Different color sof things like parallle vs flatness. slider to do threshold of tolernace levels. 

I'm still not seeing the right side panel pop in fo rthe heat map. its only showing on the face elec ttool. 
when the mouse is over the right or left panel area, it shouldn't scroll or rotate the part. the mouse needs to eb over the cad viewport area to do these functions 


get rid of the grid dots feature altogether.  get rid of snaps

hide axis by default 

panel expander icon shoul dbe a right or left carot 

redo all the branding on the pap to be Scribe. Scribe is hte new name of this repo, the tool. We should have the logo text in the ipper elft be SCRIBE in a bont but clean font. The subtitle should be "like PDFs for CAD"

default model to load should always be tests\sample.STEP. think about how we could preload this fast. 

the cube face clck to snap to an orthogonal view feature still didn't work. make sure we're raycasting from mouse pointer to the cube face. 

make all the dimensiosn default to inches. Our tolerance bands should reflect normal inch bands for machined parts. 

the heat map panel ops up now. but we need to reconsider how we're shading the faces in heat map mode. We want to visually highlight the tighter tolerances in the red color. The looser tolerances should be in default gray color. We should be able to set the color picker for both the lower and upper tolerance bands in the heat map settings right side panel. think about how to implement this comprehensively. 

we should default to the isometric view on page load. 

get rid of grid and axes functionality and remove from top menu bar

fix the colors of the scribe logo and subtitle  improve aesthetics per your best jdugement. 

we need to tighten up the tolerane bands. We seldrom have tolerances ighter than .0001 and looser than .03 inches 
we should have check boxes in the heat map settings to enable or disable the different types of tolerance callouts. 
we need t ahve a color picker and bilateral sliders on the heat map settings to set the color of the tight and loose tolerance bands.  like a dual slider setup 

change the export colored step button to just say export. 


we should do a similar approach to the hole wizard as the heap map. We should have a list of all the threads in the model in an expanding groups for each thrad type. We should have a color picker for each thread type. 

the cube oerpsective clicker isn't working. Can you come up with an alternative way to do this that's more reliable. 

can the default view be changed to isometric that's halfway between the front, left and bottom view? 

get rid of the tolerances mnenu and button 

the quick views thing needs to embeded in the viewport, not hte hole wizard meny. Needs to be icons in the viewport. 

the hole wizard shouldn't analyze the model for diameters. it should rather look at the metadata to extract the hole data that is user defined. 

the default value / class in the propeties dropdown menuy shoul dbe more suited for inch parts. with values quick values between .0005 and .03

there's some sort of weird centered glitch when I xoom after a pan, it tries to auto center and model and creates a jerk zoom effect. we shouldn't do this, it needs to remain buttery smooth, we shouldn't try to auto adjust like this. 

the hole wizard isn't seeing the whole meta data. No holes detected.

update the system_prompt.md file to reflect all these changes, along with the readme. 

the hoel wiard button is popping up the face menu panel, not the hole wizard panel 

add drop downs and metadata fields for roughness. Delete the finish process. Delete material and hardness fields. 

the hole wizard panel popup is being propblematic. We should structure it as a hole new panel. We should have like mini tabs on the right side, where you click the little tab and it pops out the right panel. Keel in mind we have different panels for face properties, heatmap, and hole wizard. Do this restructure to the html, css, js and backend. 

hole wizard still isn't detecting hole dat ain the metadata. it sayd V"Load a model to see holes...". we need it to rescan the metadata and populate the list of holes as we update them in face manager, or if we load in a new model. understand? shouldn't be stale. 


there's a glitch where when we zoom there is some sort of auto-centering that happens. It's not smooth. We need to get rid of this. 

hole wizard is now recognizing hole groups. We need to assign a color to each group, making all other model face slight gray, so we can turn on hoel groups for easy ID. This coloring mode hsould persist as long as the holes panel is up. 

get rid of the roating cube thing in the bottom left 

the delete x button didn't actually delete the thread metadata. we ned to delete and rescan the metadata to update the hole groups. 19Failed to delete group: ReferenceError: syncBatchThread is not defined

get rid of rotating cube in bottom left corner. 

change export colored step to just export step button

we need to be saving the metadata to the db during all these updates. 

we need an x icon optiont o delete the tolerance group, similar to how we can delete holes. implement this. 


as a sarting point for the tolerance group color, we should grab the color that face already has from the model or the face manager or the hole data. we should always prefer this color over the default color. 